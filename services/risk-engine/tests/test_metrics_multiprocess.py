"""/metrics must aggregate across uvicorn workers (prometheus multiprocess mode).

Without it each worker serves only its own counters and Prometheus scrapes a
random one, so counters appear to jump backwards. Subprocesses stand in for
workers; metrics.py is loaded standalone (it only depends on prometheus_client).
"""
import os
import subprocess
import sys
from pathlib import Path

METRICS = Path(__file__).resolve().parent.parent / "metrics.py"

_CHILD = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("m", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
if sys.argv[2] == "inc":
    m.REPLAY_DETECTED.inc()
else:
    sys.stdout.write(m.render_latest().decode())
"""


def _run(mode, mpdir):
    env = dict(os.environ, PROMETHEUS_MULTIPROC_DIR=str(mpdir))
    out = subprocess.run(
        [sys.executable, "-c", _CHILD, str(METRICS), mode],
        env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout


def test_metrics_aggregate_across_worker_processes(tmp_path):
    mpdir = tmp_path / "prom"  # absent: metrics.py must create it (tmpfs starts empty)
    _run("inc", mpdir)
    _run("inc", mpdir)
    text = _run("render", mpdir)
    assert 'aztdp_replay_detected_total 2.0' in text, text
