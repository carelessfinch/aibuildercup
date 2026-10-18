from __future__ import annotations

import io
import json

from jobs.run_plan import execute_plan, make_emitter, plan_from_spec


def plan_dict() -> dict[str, object]:
    return {
        "case_id": "plasma_cf4o2_icp_v1",
        "question": "Validate ion flux against experiment.",
        "solver": "plasma_global_model",
        "chemistry_ref": "chemistry_ar_lieberman.yaml",
        "operating_point": {
            "power_W": 100,
            "pressure_mTorr": 15,
            "flow_sccm": {"CF4": 40, "O2": 10},
            "bias_sweep_V": [0, 25, 50, 75, 100],
        },
    }


def test_run_plan_emits_one_whole_sweep_and_writes_clean_output(tmp_path) -> None:
    stream = io.StringIO()
    output = tmp_path / "result.json"
    plan = plan_from_spec({"plan": plan_dict()})
    result = execute_plan(plan, make_emitter(stream), output_path=str(output))

    assert output.is_file()
    assert result["status"] == "complete"
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [event["event"] for event in events] == [
        "job_started",
        "solver_completed",
        "job_completed",
    ]
    assert events[0]["data"]["sweep_points"] == 5
    assert events[0]["data"]["granularity"] == "one_job_per_plan_or_sweep"
    assert len(result["results"]) == 5


def test_plan_from_spec_accepts_a_direct_plan() -> None:
    plan = plan_from_spec(plan_dict())
    assert plan.case_id == "plasma_cf4o2_icp_v1"
    assert len(plan.operating_point.bias_sweep_V) == 5
