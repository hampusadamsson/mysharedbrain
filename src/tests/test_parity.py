"""Contract: API and MCP mirror each other — no drift in either direction.

Every MCP tool maps to REST route(s); every /api route maps back to a tool.
Resources/prompts (MCP-native) and health/SPA/docs (HTTP-only) are out of scope.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from fastmcp import Client

from mysharedbrain.app import create_app
from mysharedbrain.mcp import mcp

ID = "/api/notes/{note_id:path}"

TOOL_ROUTES: dict[str, set[tuple[str, str]]] = {
    "create_note": {("POST", "/api/notes")},
    "read_note": {("GET", ID)},
    "read_notes": {("POST", "/api/notes/batch")},
    "list_notes": {("GET", "/api/notes")},
    "list_directory": {("GET", "/api/browse")},
    "update_note": {("PUT", ID)},
    "append_note": {("POST", ID + "/append")},
    "patch_note": {("PATCH", ID)},
    "delete_note": {("DELETE", ID)},
    "restore_note": {("POST", ID + "/restore")},
    "move_note": {("POST", ID + "/move")},
    "search_notes": {("GET", "/api/search")},
    "search_by_tag": {("GET", "/api/tags/{tag}")},
    "get_frontmatter": {("GET", ID + "/meta")},
    "set_frontmatter": {("PUT", ID + "/meta")},
    "get_backlinks": {("GET", ID + "/backlinks")},
    "note_history": {("GET", ID + "/history")},
    "get_outgoing": {("GET", ID + "/outgoing")},
    "recent_changes": {("GET", "/api/audit")},
    "list_capture": {("GET", "/api/capture")},
    "give_feedback": {("POST", "/api/feedback")},
    "review_capture": {("POST", "/api/capture/{entry_id}/review")},
    "set_capture_status": {("PUT", "/api/capture/{entry_id}/status")},
    "ask_question": {("POST", "/api/request")},
    "get_settings": {("GET", "/api/settings")},
    "update_settings": {("PUT", "/api/settings")},
    "run_job": {("POST", "/api/settings/jobs/{job_id}/run")},
    "test_mcp_server": {("POST", "/api/settings/mcp/test")},
    "test_model": {("POST", "/api/settings/model/test")},
    "list_model_providers": {("GET", "/api/settings/providers")},
    "list_job_runs": {("GET", "/api/settings/jobs/{job_id}/runs")},
}


def _iter_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Yield leaf routes, expanding ``include_router`` wrappers.

    FastAPI >=0.140 keeps included routers lazy as ``_IncludedRouter``
    placeholders, so the leaf routes are reached via ``original_router``.
    """
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_routes(original.routes)
        else:
            yield route


def api_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in _iter_routes(create_app().routes):
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", "")
        if methods and path.startswith("/api"):
            routes.update((m, path) for m in sorted(methods))
    return routes


def test_every_mapped_route_exists() -> None:
    known = api_routes()
    for tool, routes in TOOL_ROUTES.items():
        for route in routes:
            assert route in known, f"{tool} maps to missing route {route}"


def test_every_api_route_has_a_tool() -> None:
    covered = {r for routes in TOOL_ROUTES.values() for r in routes}
    for route in api_routes():
        assert route in covered, f"API route {route} has no MCP tool"


async def test_every_registered_tool_is_mapped() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    registered = {t.name for t in tools}
    assert registered == set(TOOL_ROUTES), f"drift: {registered ^ set(TOOL_ROUTES)}"
