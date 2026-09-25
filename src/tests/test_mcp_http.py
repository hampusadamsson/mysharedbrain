"""MCP over Streamable HTTP: POST /mcp speaks MCP on the same app (API+UI+MCP)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from mysharedbrain.app import create_app

_HEADERS = {"Accept": "application/json, text/event-stream"}
_URL = "/mcp/"


def _session(client: TestClient) -> str:
    """MCP handshake: initialize, then report the session id."""
    response = client.post(
        _URL,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers=_HEADERS,
    )
    assert response.status_code == 200, response.text[:300]
    session = response.headers.get("mcp-session-id")
    assert session, "server must return an MCP session id"
    initialized = client.post(
        _URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={**_HEADERS, "mcp-session-id": session},
    )
    assert initialized.status_code in (200, 202), initialized.text[:300]
    return session


def _payload(response: Any) -> Any:
    """Streamable HTTP answers JSON or SSE-framed JSON — unwrap either."""
    if "text/event-stream" in response.headers.get("content-type", ""):
        data = "\n".join(
            line[5:].strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        )
        return json.loads(data)
    return response.json()


def _rpc(
    client: TestClient, session: str, method: str, params: dict[str, Any], rpc_id: int
) -> dict[str, Any]:
    response = client.post(
        _URL,
        json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
        headers={**_HEADERS, "mcp-session-id": session},
    )
    assert response.status_code == 200, response.text[:300]
    body = _payload(response)
    assert "error" not in body, body
    return body["result"]  # type: ignore[no-any-return]


def test_mcp_http_lists_tools_and_calls_one(vault_dir: Path) -> None:
    """Handshake, tools/list, then a real tool call over HTTP."""
    with TestClient(create_app()) as client:
        session = _session(client)
        tools = _rpc(client, session, "tools/list", {}, 2)["tools"]
        names = {tool["name"] for tool in tools}
        assert {"create_note", "read_note", "search_notes"} <= names

        created = _rpc(
            client,
            session,
            "tools/call",
            {"name": "create_note", "arguments": {"note_id": "http", "content": "hi"}},
            3,
        )
        assert created["isError"] is False
        assert "http" in str(created["content"])
        assert (vault_dir / "http.md").read_text(encoding="utf-8") == "hi"


def test_mcp_http_does_not_fall_into_spa(vault_dir: Path) -> None:
    """Unknown /mcp/* paths stay JSON 404s, never index.html."""
    with TestClient(create_app()) as client:
        response = client.post(
            "/mcp/does-not-exist/",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=_HEADERS,
        )
        assert response.status_code == 404
        assert "text/html" not in response.headers.get("content-type", "")


def test_mcp_http_bare_path_redirects_to_slash(vault_dir: Path) -> None:
    """Bare /mcp 307-redirects (method+body preserved), never SPA html."""
    with TestClient(create_app(), follow_redirects=False) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=_HEADERS,
        )
        assert response.status_code == 307
        assert response.headers["location"].endswith("/mcp/")
