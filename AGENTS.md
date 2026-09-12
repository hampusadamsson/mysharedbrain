# AGENTS.md — mysharedbrain

TDD: write/extend `src/tests/` first, then implement. `main` is always green
(`uv run pytest src/tests/ -q`, `ruff check`, `ruff format --check`, `basedpyright`).

## Commands

```bash
uv sync                    # install (Python 3.13)
uv run pytest src/tests/ -q
uv run ruff check src/ && uv run ruff format --check src/
uv run basedpyright
uv run mysharedbrain       # API + UI :8000 (VAULT_DIR, default ./vault)
uv run mysharedbrain --mcp # MCP server over stdio
```

## Architecture

Single audited mutation path: `service.Librarian` (actor-tagged). `app.py`
(REST) and `mcp.py` (7 tools) are thin adapters — never mutate the vault
behind the librarian. State: markdown notes + `.brain/capture.jsonl` queue +
`.brain/audit.jsonl` log. Search: ripgrep with pure-Python fallback.
`frontend/` is static and talks HTTP JSON only — no imports from `src/`.
