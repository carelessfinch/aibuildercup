"""Typed runtime configuration with environment overrides for the agent layer."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "base.yaml"

FlowMode = Literal["graph", "coordinator"]


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str


class FlowSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: FlowMode
    include_etch: bool = False


class ReviewSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_rounds: int = Field(ge=1, le=3)


class SolverSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: str


class LitragSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index_dir: str
    embed_backend: str


class AgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    agent: AgentSettings
    flow: FlowSettings
    review: ReviewSettings
    solver: SolverSettings
    litrag: LitragSettings


def _env_overrides(environ: Mapping[str, str]) -> dict[str, dict[str, str]]:
    overrides: dict[str, dict[str, str]] = {}

    def set_value(section: str, key: str, env_name: str, transform=None) -> None:
        value = environ.get(env_name)
        if value is not None and value != "":
            overrides.setdefault(section, {})[key] = (
                transform(value) if transform else value
            )

    set_value("agent", "model", "AGENT_MODEL")
    set_value("flow", "mode", "FLOW_MODE")
    set_value("flow", "include_etch", "FLOW_INCLUDE_ETCH", _env_bool)
    set_value("review", "max_rounds", "REVIEW_MAX_ROUNDS", int)
    set_value("solver", "backend", "SOLVER_BACKEND")
    set_value("litrag", "index_dir", "LITRAG_INDEX_DIR")
    set_value("litrag", "embed_backend", "LITRAG_EMBED_BACKEND")
    return overrides


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(
    path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AgentRuntimeConfig:
    """Load configs/base.yaml and apply the agent layer's documented overrides."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    values = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        msg = f"{config_path}: expected a YAML object"
        raise ValueError(msg)

    for section, section_values in _env_overrides(
        os.environ if environ is None else environ
    ).items():
        values.setdefault(section, {}).update(section_values)
    return AgentRuntimeConfig.model_validate(values)
