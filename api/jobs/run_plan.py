"""Cloud Run Job entrypoint for one plasma sweep or complete simulation plan.

Contract:
* one job reads one run spec and executes one plan/sweep (never one point);
* progress is structured NDJSON on stdout;
* the final state is written atomically to ``--output``/``RUN_OUTPUT_PATH``;
* solver internals may still be pending, but the job plumbing is complete.

M2's Cloud Run adapter in ``simtools.runner`` will submit this entrypoint when
``solver.backend=cloud_run_job``. The local backend remains supported for evals.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from agents.contracts import SimulationPlan

ProgressSink = Callable[[str, str, dict[str, Any]], None]


class JobError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def make_emitter(stream: TextIO | None = None) -> ProgressSink:
    output = stream if stream is not None else sys.stdout

    def emit(event: str, level: str = "info", data: dict[str, Any] | None = None) -> None:
        record = {
            "timestamp": utc_now(),
            "level": level,
            "event": event,
            "job": os.getenv("CLOUD_RUN_JOB", "local"),
            "task_index": int(os.getenv("CLOUD_RUN_TASK_INDEX", "0")),
            "data": data or {},
        }
        output.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
        output.flush()

    return emit


def load_spec(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        spec_path = Path(path)
        if not spec_path.is_file():
            raise JobError(f"run spec does not exist: {path}")
        raw = spec_path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JobError(f"run spec is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise JobError("run spec must be a JSON object")
    return value


def plan_from_spec(spec: dict[str, Any]) -> SimulationPlan:
    """Accept either a plan directly or ``{"schema": "...", "plan": {...}}``."""

    payload = spec.get("plan", spec)
    try:
        return SimulationPlan.model_validate(payload)
    except ValidationError as exc:
        raise JobError(f"run spec does not match SimulationPlan: {exc}") from exc


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, default=str)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def resolve_chemistry_path(reference: str) -> Path:
    direct = Path(reference)
    if direct.is_file():
        return direct
    bundled = Path(__file__).resolve().parent.parent / "simtools" / "data" / Path(reference).name
    if bundled.is_file():
        return bundled
    raise JobError(f"chemistry data not found: {reference}")


def execute_plan(
    plan: SimulationPlan,
    emit: ProgressSink,
    *,
    output_path: str | None = None,
) -> dict[str, Any]:
    from simtools.chemistry import load_chemistry
    from simtools.plasma import run_sweep

    emit(
        "job_started",
        data={
            "case_id": plan.case_id,
            "solver": plan.solver,
            "chemistry_ref": plan.chemistry_ref,
            "sweep_points": len(plan.operating_point.bias_sweep_V),
            "granularity": "one_job_per_plan_or_sweep",
        },
    )

    try:
        chemistry = load_chemistry(resolve_chemistry_path(plan.chemistry_ref))
        if chemistry.status != "ready":
            raise NotImplementedError(
                f"chemistry {chemistry.id!r} is {chemistry.status}; supply rates before solving"
            )
        results = run_sweep(chemistry, plan.operating_point)
        output = {
            "status": "complete",
            "plan": plan.model_dump(mode="json"),
            "results": [result.model_dump(mode="json") for result in results],
        }
        emit("solver_completed", data={"points": len(results), "status": "complete"})
    except NotImplementedError as exc:
        output = {
            "status": "solver_pending",
            "plan": plan.model_dump(mode="json"),
            "detail": str(exc),
        }
        emit("solver_pending", level="warning", data={"detail": str(exc)})

    destination = Path(output_path or os.getenv("RUN_OUTPUT_PATH", "/tmp/plasma-run-result.json"))
    atomic_write(destination, output)
    emit("job_completed", data={"status": output["status"], "output": str(destination)})
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one simulation plan as a single Cloud Run Job."
    )
    parser.add_argument(
        "--spec",
        default=os.getenv("RUN_SPEC_PATH"),
        help="Run-spec JSON path, or - for stdin (default: RUN_SPEC_PATH).",
    )
    parser.add_argument("--output", help="Final JSON output path (default: RUN_OUTPUT_PATH).")
    args = parser.parse_args(argv)

    if not args.spec:
        parser.error("--spec or RUN_SPEC_PATH is required")
    emit = make_emitter()
    try:
        plan = plan_from_spec(load_spec(args.spec))
        emit("plan_validated", data={"case_id": plan.case_id, "solver": plan.solver})
        execute_plan(plan, emit, output_path=args.output)
        return 0
    except JobError as exc:
        emit("job_failed", level="error", data={"detail": str(exc)})
        return 2
    except Exception as exc:
        emit("job_failed", level="error", data={"error": str(exc), "kind": type(exc).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
