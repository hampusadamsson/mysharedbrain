# MySharedBrain

[![CI Backend](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml)
[![Docker Build & Push](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/docker.yml/badge.svg)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/docker.yml)

An information management system meant for AI. A fully fledged markdown vault
wiki: view it as a wiki in the web UI, CRUD any page, move notes, search by
name or content. One note = one `.md` file, folders = real folders, flat or
nested.

Think of it as a **librarian**: ask for information and it is presented when
available; missing information is **logged for future action** so the librarian
can retrieve it later. The **feedback** function is the improvement queue —
edits, missing-info notes, requests. In increments the librarian
**processes the capture queue** (reviewed and double-checked) before updating
the vault. All changes to the vault and the queue are **audited** (like git).
Mutations flow through one audited service layer, exposed to agents via **MCP**.

## Repo layout

```
src/mysharedbrain/   backend (uv · Python 3.13 · FastAPI · FastMCP)
  vault.py           CRUD + move + ripgrep search over markdown files
  capture.py         feedback queue (pending → applied/approved/rejected)
  audit.py           append-only JSONL audit log (like git log)
  service.py         the librarian: single audited mutation path
  app.py             REST API + serves the UI
  mcp.py             MCP server (7 tools)
frontend/            decoupled static UI (no build; HTTP JSON only)
Dockerfile           single runtime image (backend serves the UI)
```

## Quickstart (local dev)

You need [uv](https://github.com/astral-sh/uv).

```bash
cp .env.example .env   # set VAULT_DIR (default ./vault)
uv sync
uv run pytest src/tests/ -q      # TDD: tests first, always green on main
uv run mysharedbrain             # API + UI on http://localhost:8000
uv run mysharedbrain --mcp       # MCP server over stdio
```

## MCP tools

| Tool | Description |
| ---- | ----------- |
| `create_note` | Create note |
| `read_note` | Read note by id |
| `update_note` | Update note by id |
| `delete_note` | Delete note by id |
| `move_note` | Move/rename note |
| `search_notes` | Search names + content (ripgrep) |
| `give_feedback` | Correct info · flag missing info · file a request |
| `ask_question` | Ask the librarian; misses are logged for future retrieval |

Add to an MCP client (stdio):

```json
{ "mcpServers": { "mysharedbrain": {
  "command": "uv", "args": ["run", "mysharedbrain", "--mcp"],
  "cwd": "/path/to/mysharedbrain",
  "env": { "VAULT_DIR": "/path/to/vault" }
} } }
```

## REST API

Notes `POST/GET/PUT/DELETE /api/notes…` (+ `/move`), `GET /api/search?q=`,
`POST /api/feedback`, `GET /api/capture`, `POST /api/capture/{id}/review`,
`POST /api/request`, `GET /api/audit`, `GET /health`.

## Docker

```bash
docker build -t mysharedbrain .
docker run -p 8000:8000 -v mysharedbrain-data:/data/vault mysharedbrain
```

Images are published to `ghcr.io/hampusadamsson/mysharedbrain` (`sha-<sha>`,
`latest` on `main`).

## Vault layout

```
$VAULT_DIR/
  <note-id>.md        notes, flat or in real folders
  .brain/
    capture.jsonl     feedback queue (JSONL, one entry per line)
    audit.jsonl       append-only change history (JSONL)
```
