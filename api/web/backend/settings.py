"""Runtime settings loaded from configs/base.yaml and environment variables.

Secrets never enter this module: it only reads non-secret wiring and limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "base.yaml"


def _env_int(name: str, default: int) -> int:
    raw = _getenv(name)
    return int(raw) if raw is not None else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _getenv(name: str) -> str | None:
    import os

    value = os.getenv(name)
    return value if value not in {None, ""} else None


@dataclass(frozen=True)
class WebSettings:
    """Non-secret web settings; every value can be overridden in deployment."""

    flow_backend: str = "mock"
    flow_mode: str = "graph"
    flow_include_etch: bool = False
    review_max_rounds: int = 3
    run_task_delay_s: float = 0.05
    rate_limit_per_ip_per_hour: int = 5
    daily_run_cap: int = 30
    max_concurrent_runs: int = 2
    spend_killswitch: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    litrag_api_url: str | None = None
    litrag_service_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_max_rounds", min(3, max(1, self.review_max_rounds)))

    @classmethod
    def load(cls) -> WebSettings:
        config_path = Path(_getenv("WEB_CONFIG_PATH") or DEFAULT_CONFIG_PATH)
        values: dict[str, Any] = {}
        if config_path.exists():
            values = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        flow = values.get("flow", {})
        review = values.get("review", {})
        web = values.get("web", {})
        origins = _getenv("WEB_CORS_ORIGINS")
        flow_backend = _getenv("WEB_FLOW_BACKEND") or str(web.get("flow_backend", "mock"))
        return cls(
            flow_backend=flow_backend,
            flow_mode=_getenv("FLOW_MODE") or str(flow.get("mode", "graph")),
            flow_include_etch=_env_bool(
                "FLOW_INCLUDE_ETCH", bool(flow.get("include_etch", False))
            ),
            review_max_rounds=min(
                3,
                max(
                    1,
                    _env_int("REVIEW_MAX_ROUNDS", int(review.get("max_rounds", 3))),
                ),
            ),
            run_task_delay_s=float(
                _getenv("WEB_RUN_TASK_DELAY_S")
                if _getenv("WEB_RUN_TASK_DELAY_S") is not None
                else 0.05
            ),
            rate_limit_per_ip_per_hour=_env_int(
                "WEB_RATE_LIMIT_PER_IP_PER_HOUR",
                int(web.get("rate_limit_per_ip_per_hour", 5)),
            ),
            daily_run_cap=_env_int("WEB_DAILY_RUN_CAP", int(web.get("daily_run_cap", 30))),
            max_concurrent_runs=_env_int(
                "WEB_MAX_CONCURRENT_RUNS", int(web.get("max_concurrent_runs", 2))
            ),
            spend_killswitch=_env_bool(
                "WEB_SPEND_KILLSWITCH", bool(web.get("spend_killswitch", False))
            ),
            cors_origins=tuple(
                item.strip() for item in origins.split(",") if item.strip()
            )
            if origins
            else ("http://localhost:5173",),
            litrag_api_url=_getenv("LITRAG_API_URL") or None,
            litrag_service_key=_getenv("SERVICE_KEY") or None,
        )
