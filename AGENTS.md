# AGENTS.md — mysharedbrain

TDD: write/extend tests first, then implement. `main` is always green:
backend (`uv run pytest src/tests/ -q`, `ruff check`, `ruff format --check`,
`basedpyright`) and frontend (`pnpm check`, `pnpm lint`, `pnpm test`).

## Commands

```bash
# backend (repo root)
uv sync                    # install (Python 3.13)
uv run pytest src/tests/ -q
uv run ruff check src/ && uv run ruff format --check src/
uv run basedpyright
uv run mysharedbrain       # API only :8000 (VAULT_DIR, default ./vault)
uv run mysharedbrain --mcp # MCP server over stdio

# frontend (frontend/)
pnpm install
pnpm dev                   # vite dev server, proxies /api + /health to :8000
pnpm check && pnpm lint && pnpm test && pnpm build
```

Local dev runs two processes: `uv run mysharedbrain` (API) and `pnpm dev` (UI).
In the image the API also serves the built UI (`/app/static`, SvelteKit
adapter-static with SPA fallback) — one container, one port.

## Architecture

Single audited mutation path: `service.Librarian` (actor-tagged). `app.py`
(REST) and `mcp.py` (tools/resources/prompts) are thin adapters — never mutate
the vault behind the librarian. State: markdown notes + `.brain/capture.jsonl`
queue + `.brain/audit.jsonl` log. Search: ripgrep with pure-Python fallback.

Frontend: SvelteKit 2 + Svelte 5 runes + TypeScript, Tailwind v4,
shadcn-svelte (vega/lucide), adapter-static SPA. Talks HTTP JSON only via
`src/lib/api/client.ts` — no imports from `src/` (decoupling contract).
Routes: `/`, `/ask`, `/capture`, `/activity`, `/search`, `/p/[...id]`.
Markdown is rendered with `marked` + DOMPurify (never hand-rolled).
Component tests run in Chromium (vitest browser mode).
