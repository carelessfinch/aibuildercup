"""Solver run backends: local (dev/evals) and cloud_run_job (M2, W5).

Decision H6: one job per sweep or plan, never per point — a global-model
point runs in under a second while a Cloud Run Job start takes many seconds.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any


class LocalRunner:
    """In-process backend used by evals and local `adk web` runs."""

    def __init__(self) -> None:
        self._runs: dict[str, tuple[Callable[[], Any], Any | None]] = {}

    def submit(self, fn: Callable[[], Any]) -> str:
        run_id = f"local-{uuid.uuid4().hex[:12]}"
        self._runs[run_id] = (fn, None)
        return run_id

    def await_result(self, run_id: str) -> Any:
        fn, result = self._runs[run_id]
        if result is None:
            result = fn()
            self._runs[run_id] = (fn, result)
        return result


def get_runner(backend: str = "local") -> LocalRunner:
    """Return a runner for the configured backend (configs/base.yaml: solver.backend)."""
    if backend == "local":
        return LocalRunner()
    if backend == "cloud_run_job":
        raise NotImplementedError("W5 wires Cloud Run Jobs (one job per sweep/plan)")
    msg = f"unknown solver backend: {backend!r}"
    raise ValueError(msg)
