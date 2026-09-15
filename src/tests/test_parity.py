"""Contract: API and MCP mirror each other — no drift in either direction.

Every MCP tool maps to REST route(s); every /api route maps back to a tool.
Resources/prompts (MCP-native) and health/SPA/docs (HTTP-only) are out of scope.
"""

from __future__ import annotations

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
    "move_note": {("POST", ID + "/move")},
    "search_notes": {("GET", "/api/search")},
    "search_by_tag": {("GET", "/api/tags/{tag}")},
    "get_frontmatter": {("GET", ID + "/meta")},
    "set_frontmatter": {("PUT", ID + "/meta")},
    "get_backlinks": {("GET", ID + "/backlinks")},
    "get_outgoing": {("GET", ID + "/outgoing")},
    "recent_changes": {("GET", "/api/audit")},
    "list_capture": {("GET", "/api/capture")},
    "give_feedback": {("POST", "/api/feedback")},
    "review_capture": {("POST", "/api/capture/{entry_id}/review")},
    "ask_question": {("POST", "/api/request")},
}


def api_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in create_app().routes:
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
