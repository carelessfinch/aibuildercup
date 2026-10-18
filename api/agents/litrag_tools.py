"""Failure-isolated ADK wrappers around local or HTTP litrag tools."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

HTTP_TIMEOUT_S = 20.0


def _new_http_client(base_url: str) -> httpx.Client:
    """Create the internal rag-api client; tests monkeypatch this factory."""
    return httpx.Client(base_url=base_url, timeout=HTTP_TIMEOUT_S)


def _http_headers() -> dict[str, str]:
    service_key = os.environ.get("SERVICE_KEY", "")
    return {"X-Service-Key": service_key} if service_key else {}


def _http_backend(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = os.environ.get("LITRAG_API_URL", "").rstrip("/")
    if not base_url:
        msg = "LITRAG_API_URL is not configured"
        raise RuntimeError(msg)
    with _new_http_client(base_url) as client:
        response = client.request(
            method, path, json=json, params=params, headers=_http_headers()
        )
        response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        msg = f"{path} returned {type(payload).__name__}, expected an object"
        raise TypeError(msg)
    return payload


def _should_use_http() -> bool:
    return bool(os.environ.get("LITRAG_API_URL", "").strip())


def _litrag_tools() -> tuple[
    Callable[..., dict[str, Any]],
    Callable[..., dict[str, Any]],
    Callable[[], dict[str, Any]],
]:
    """Import the local litrag module lazily; optional deps stay tool-level."""
    try:
        from litrag.litrag.tools import (
            list_literature_sources,
            read_source_pages,
            search_literature,
        )
    except ImportError as exc:
        raise RuntimeError("literature index unavailable: litrag import failed") from exc
    return search_literature, read_source_pages, list_literature_sources


def _unavailable(operation: str, exc: Exception) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "operation": operation,
        "error_message": f"literature index unavailable: {type(exc).__name__}: {exc}",
        "results": [],
    }


def safe_search_literature(
    query: str,
    top_k: int = 3,
    source_ids: list[str] | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Search litrag without letting a missing private index crash an agent tool."""
    if _should_use_http():
        try:
            return _http_backend(
                "POST",
                "/v1/search",
                json={
                    "query": query,
                    "top_k": top_k,
                    "source_ids": source_ids,
                    "kind": kind,
                },
            )
        except Exception as exc:  # noqa: BLE001 - tool failures stay structured
            return _unavailable("search_literature", exc)
    try:
        search, _, _ = _litrag_tools()
        return search(query, top_k=top_k, source_ids=source_ids, kind=kind)
    except Exception as exc:  # noqa: BLE001
        return _unavailable("search_literature", exc)


def safe_read_source_pages(
    source_id: str, first_pdf_page: int, last_pdf_page: int | None = None
) -> dict[str, Any]:
    """Read litrag pages without exposing an index-loading failure as a crash."""
    if _should_use_http():
        params: dict[str, Any] = {"first": first_pdf_page}
        if last_pdf_page is not None:
            params["last"] = last_pdf_page
        try:
            return _http_backend(
                "GET", f"/v1/sources/{source_id}/pages", params=params
            )
        except Exception as exc:  # noqa: BLE001
            return _unavailable("read_source_pages", exc)
    try:
        _, read_pages, _ = _litrag_tools()
        return read_pages(source_id, first_pdf_page, last_pdf_page)
    except Exception as exc:  # noqa: BLE001
        return _unavailable("read_source_pages", exc)


def safe_list_literature_sources() -> dict[str, Any]:
    """List indexed sources, returning a stable unavailable result if needed."""
    if _should_use_http():
        try:
            return _http_backend("GET", "/v1/sources")
        except Exception as exc:  # noqa: BLE001
            return _unavailable("list_literature_sources", exc)
    try:
        _, _, list_sources = _litrag_tools()
        return list_sources()
    except Exception as exc:  # noqa: BLE001
        return _unavailable("list_literature_sources", exc)
