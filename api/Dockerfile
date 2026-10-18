FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    RESEARCH_API_CONTAINER=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY agents ./agents
COPY simtools ./simtools
COPY web/backend ./web/backend
COPY configs ./configs
COPY litrag/litrag ./litrag/litrag
# Web presets list every public eval case and reuse the harness's fault injection.
COPY evals/__init__.py evals/harness.py ./evals/
COPY evals/cases ./evals/cases
COPY evals/fixtures ./evals/fixtures

EXPOSE 8080
CMD ["sh", "-c", "uvicorn web.backend.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
