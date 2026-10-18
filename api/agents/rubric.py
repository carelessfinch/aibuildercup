"""Path helpers for the Professor's fixed rubrics."""

from __future__ import annotations

from pathlib import Path

RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"


def rubric_path(name: str = "plasma.yaml") -> Path:
    """Return an existing rubric path; keep case selection explicit at call sites."""
    path = RUBRIC_DIR / name
    if not path.is_file():
        msg = f"rubric does not exist: {path}"
        raise FileNotFoundError(msg)
    return path
