"""P5.5 — Telemetry executor drain test.

Verifies that in-flight telemetry events are not silently dropped on shutdown:
- All submitted tasks complete before shutdown_executor() returns.
- The executor refuses new submissions after shutdown.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_executor():
    return ThreadPoolExecutor(max_workers=4, thread_name_prefix="test-telemetry")


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestTelemetryDrain:
    def test_submitted_tasks_complete_before_shutdown_returns(self):
        """All submitted tasks must finish before shutdown_executor() returns."""
        completed: List[int] = []
        latch = threading.Event()
        executor = _make_executor()

        def slow_task(n: int):
            latch.wait(timeout=5)
            completed.append(n)

        for i in range(10):
            executor.submit(slow_task, i)

        # Release all tasks simultaneously then immediately shut down
        latch.set()
        executor.shutdown(wait=True, cancel_futures=False)

        assert len(completed) == 10, (
            f"Expected 10 tasks to complete before shutdown, got {len(completed)}"
        )

    def test_shutdown_executor_rejects_new_submissions(self):
        """After shutdown, submitting a new task must raise RuntimeError."""
        executor = _make_executor()
        executor.shutdown(wait=True)

        with pytest.raises(RuntimeError):
            executor.submit(lambda: None)

    def test_emit_async_drops_quietly_after_shutdown(self, monkeypatch):
        """emit_async must not raise after the executor is shut down."""
        import os
        monkeypatch.setenv("AZTDP_TELEMETRY_URL", "http://fake-telemetry:9999")
        monkeypatch.setenv("AZTDP_INTERNAL_TOKEN", "test-token")

        import importlib
        import sys

        # Reload to get a fresh module-level executor
        if "gateway.telemetry" in sys.modules:
            del sys.modules["gateway.telemetry"]
        if "gateway.config" in sys.modules:
            del sys.modules["gateway.config"]

        import gateway.config as gconfig
        import gateway.telemetry as tel

        # Shut the executor down manually
        tel._executor.shutdown(wait=True)

        # emit_async must swallow the RuntimeError without propagating
        tel.emit_async("policy_decision", {"request_id": "test-123"})  # no exception

    def test_emit_async_no_op_without_telemetry_url(self, monkeypatch):
        """If TELEMETRY_URL is unset, emit_async returns immediately without submitting."""
        import sys

        if "gateway.telemetry" in sys.modules:
            del sys.modules["gateway.telemetry"]
        if "gateway.config" in sys.modules:
            del sys.modules["gateway.config"]

        monkeypatch.setenv("AZTDP_TELEMETRY_URL", "")

        import gateway.telemetry as tel

        submitted: List[bool] = []
        original_submit = tel._executor.submit

        def tracking_submit(*args, **kwargs):
            submitted.append(True)
            return original_submit(*args, **kwargs)

        tel._executor.submit = tracking_submit

        tel.emit_async("policy_decision", {"request_id": "test-456"})
        assert not submitted, "emit_async must not submit when TELEMETRY_URL is empty"

    def test_concurrent_emits_all_land(self, monkeypatch):
        """Concurrent emit_async calls must all be submitted and executed."""
        posted: List[str] = []
        lock = threading.Lock()

        def fake_post(event_type, payload):
            with lock:
                posted.append(event_type)

        import sys
        if "gateway.telemetry" in sys.modules:
            del sys.modules["gateway.telemetry"]
        if "gateway.config" in sys.modules:
            del sys.modules["gateway.config"]

        monkeypatch.setenv("AZTDP_TELEMETRY_URL", "http://fake:9999")
        monkeypatch.setenv("AZTDP_INTERNAL_TOKEN", "tok")

        import gateway.telemetry as tel

        # Patch the internal _post to avoid real HTTP
        monkeypatch.setattr(tel, "_post", fake_post)

        N = 20
        threads = [
            threading.Thread(target=tel.emit_async, args=("risk_eval", {"i": i}))
            for i in range(N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        tel.shutdown_executor()
        assert len(posted) == N, f"Expected {N} events to be posted, got {len(posted)}"
