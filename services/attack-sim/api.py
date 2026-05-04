import asyncio
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI(title="aztdp-attack-sim", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SCRIPT_MAP = {
    "token_replay":        "token_replay.py",
    "privilege_escalation": "privilege_escalation.py",
    "geo_drift":           "geo_drift_attack.py",
    "anomaly_flood":       "anomaly_flood.py",
    "credential_stuffing": "credential_stuffing.py",
    "brute_force":         "brute_force.py",
}

_running: dict[str, bool] = {k: False for k in SCRIPT_MAP}
_last_result: dict[str, dict] = {}


def _sse(event_type: str, msg: str) -> str:
    return "data: " + json.dumps({"type": event_type, "msg": msg, "ts": time.time()}) + "\n\n"


async def _stream_script(script: str, attack_type: str):
    _running[attack_type] = True
    started = time.time()
    lines = 0
    error = None

    try:
        proc = await asyncio.create_subprocess_exec(
            "python", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            lines += 1
            kind = "error" if line.lower().startswith("error") else "log"
            yield _sse(kind, line)

        await proc.wait()
        if proc.returncode != 0:
            error = f"exit code {proc.returncode}"

    except Exception as exc:
        error = str(exc)
        yield _sse("error", f"Failed to start {script}: {exc}")
    finally:
        elapsed = round(time.time() - started, 2)
        _last_result[attack_type] = {"elapsed_s": elapsed, "lines": lines, "error": error, "ran_at": started}
        _running[attack_type] = False
        yield _sse("done", f"Completed in {elapsed}s ({lines} lines)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/sim/status")
def status():
    return {
        "running": {k: v for k, v in _running.items() if v},
        "last_results": _last_result,
        "any_running": any(_running.values()),
    }


@app.get("/v1/sim/status/{attack_type}")
def status_one(attack_type: str):
    if attack_type not in SCRIPT_MAP:
        raise HTTPException(status_code=404, detail="unknown_attack_type")
    return {"attack_type": attack_type, "running": _running[attack_type], "last_result": _last_result.get(attack_type)}


@app.post("/v1/sim/{attack_type}")
async def run_attack(attack_type: str):
    if attack_type not in SCRIPT_MAP:
        raise HTTPException(status_code=404, detail="unknown_attack_type")
    if _running[attack_type]:
        raise HTTPException(status_code=409, detail="attack_already_running")

    async def gen():
        yield _sse("start", f"Launching {attack_type}")
        async for chunk in _stream_script(SCRIPT_MAP[attack_type], attack_type):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/v1/sim/all/run")
async def run_all():
    if any(_running.values()):
        raise HTTPException(status_code=409, detail="attack_already_running")

    async def gen():
        yield _sse("start", f"Running all {len(SCRIPT_MAP)} attack scenarios sequentially")
        for attack_type, script in SCRIPT_MAP.items():
            yield _sse("section", f"=== {attack_type.upper().replace('_', ' ')} ===")
            async for chunk in _stream_script(script, attack_type):
                yield chunk
        yield _sse("done", "All scenarios completed")

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
