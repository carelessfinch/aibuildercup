"""Runner tests: local backend roundtrip; job granularity contract (H6)."""

import pytest

from simtools.runner import LocalRunner, get_runner


def test_local_runner_roundtrip() -> None:
    runner = get_runner("local")
    assert isinstance(runner, LocalRunner)
    run_id = runner.submit(lambda: {"points": 5})
    assert runner.await_result(run_id) == {"points": 5}
    assert runner.await_result(run_id) == {"points": 5}  # cached, not re-executed


def test_cloud_run_job_backend_is_w5_scope() -> None:
    with pytest.raises(NotImplementedError, match="one job per sweep/plan"):
        get_runner("cloud_run_job")


def test_unknown_backend_rejected() -> None:
    with pytest.raises(ValueError, match="unknown solver backend"):
        get_runner("quantum")
