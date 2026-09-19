# AGENTS.md — mysharedbrain

TDD: write/extend tests first, then implement. `main` is always green:
backend (`uv run pytest src/tests/ -q`, `ruff check`, `ruff format --check`,
`basedpyright`) and frontend (`pnpm check`, `pnpm lint`, `pnpm test`).

## Commits: Conventional Commits

Every commit header is `type(scope): subject` — enforced by
`.github/workflows/commitlint.yml` (and by release-please, which reads these to
bump the version). Types: `feat`, `fix`, `perf`, `revert`, `docs`, `refactor`,
`test`, `build`, `ci`, `chore`. Lower-case type and scope, no trailing period,
header ≤ 100 chars, imperative subject.

```
feat(ask): spinner while the agent is thinking
fix(vault): accept note ids written with a .md suffix
docs: document the capture review flow
```

- `feat:` → minor bump, `fix:`/`perf:` → patch. `feat!:` or a `BREAKING CHANGE:`
  footer → major. `docs`/`refactor`/`test`/`ci`/`chore` release nothing on their
  own but still need a conventional header.
- One logical change per commit; put the reasoning in the body, not the header.
- Dependabot PRs arrive as `chore(deps): bump …` / `chore(deps-dev): …` so
  they pass the same checks and never trigger a release. Minor/patch updates are
  grouped into one PR per ecosystem (`.github/dependabot.yml`); majors come
  alone. Merging one is a normal review: read the CI result, then merge.
- Release PRs are opened automatically (`chore: release X.Y.Z`) and carry the
  version bump plus `CHANGELOG.md`. Merge it to release; the image is retagged
  `vX.Y.Z` by `.github/workflows/release-image.yml`.

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
the vault behind the librarian. State: markdown notes + `.brain/brain.db`
(sqlite: audit log + capture queue + job runs). Search: ripgrep with pure-Python
fallback.

Audit: every interaction with a file is logged against that note id — reads and
keyword `find`s included, not just writes — with a precise `action` plus a coarse
`kind` (read/find/write/move/delete/capture/job/other) used for filtering.
`Librarian.file_stats` / `file_history` take an optional note id: with one it is
the per-file view, without one it is the whole log (what Activity shows). Both
scopes return identical JSON, and `InteractionLog.svelte` renders either —
counters as filter chips, then the list.

Indexes: `db.py` owns the schema's connection/plan hygiene (`PRAGMA optimize` on
close) and `migrations/` owns the indexes, chosen from EXPLAIN QUERY PLAN output.
`src/tests/test_query_plans.py` asserts the plans, so a migration that drops or
reorders an index fails a test instead of silently slowing the vault down. Notes
are files, not rows — filename lookup is a `stat`, so there is no note index to add.

Capture kinds: `edit` | `missing` | `request` | `question`. Entries the system
files itself (an unanswered `ask`, now kind `question`) carry `automated=True`;
the UI never sends that flag, so anything a person queues stays unmarked.

Capture states: `pending` | `applied` | `approved` | `rejected`. `review()` is
guarded (pending → verdict, once); `restate()`/`restate_capture()` is the
override the UI's state dropdown uses — any → any, no vault write, audited as
`capture-<state>` with a `restate:` detail so overrides are distinguishable from
reviews.

Agent: `config.py` (Pydantic, YAML seed + database + `BRAIN__*` env overrides) feeds `agent.py`
(Pydantic-AI) with the enabled `tools.py` built-ins — vault/capture only — plus
opted-in remote MCP servers. **The librarian has no shell**: built-ins are
vault/capture operations, and MCP servers must be remote (`http`/`sse`) —
`MCPServerConfig` refuses `stdio`/`command`, because that would be local process
execution. **And its reach is the vault**: every note id is validated as a path
*and* resolved, so a symlink inside the vault cannot read or write outside it
(that was a real escape: `sub/link -> /tmp` wrote a file the vault could not
list). Each built-in tool declares a `scope` — `vault` or `capture`, the latter
being the vault's own `.brain/brain.db` — and a test fails if a tool declares
anything else. The only `subprocess` call in the codebase is ripgrep search, with
an argument list and `--`, never `shell=True`. The shipped defaults are the same
three **disabled** jobs as `brain.example.yaml`, with `scheduler.enabled: false`,
so nothing runs unprompted and Settings → Jobs still shows the intended shapes. `jobs.py` schedules runs (interval or cron) and
records them in sqlite; every mutation the agent makes is audited under the
`LIBRARIAN_ACTOR` (`librarian`) actor, and each run adds one summary audit entry
(`job-ok`/`job-error`/`job-skipped`) — so Activity answers "what did the
librarian change?" with a single filter. `api_settings.py` exposes read/write
config and manual
runs, mirroring the **Settings** UI page. Both REST and MCP can edit the config;
the agent's standing instructions are themselves a markdown note it may rewrite.

Scheduler: `jobs.py` is the only thing that fires a job on its own, and it logs
every step (start, tick, run start/ok/error/skip, next run) at INFO through
`logging_setup.configure_logging()`, called from `__main__` — without that the root
logger has no handler and INFO goes nowhere. `is_running`/`task` are public for
tests and diagnostics; `tick()` is public so a tick can be driven without the loop.

Settings storage: `BrainConfigDocument` is the schema (a plain model — validating
a *body* must not consult sources, which was a real bug when the schema and the
layering shared one class), and `BrainConfig` adds the layers: env > database >
seed file > defaults. `settings_store.SettingsStore` owns the single-row
`settings` table; `brain.yaml` is only ever read, and `config.save_config()` now
raises, as a tripwire against a second source of truth reappearing.

Connection checks: `agent.check_mcp_server` and `agent.check_model` both return
`ConnectionCheck(name, ok, detail, tools)` — one shape, one UI component
(`ConnectionStatus.svelte`). Both do the smallest real operation (list tools /
ask one word) rather than a config parse, and both redact secrets from the
message, because providers echo the key back in their errors.

Model providers: `agent.build_model` resolves any provider pydantic-ai knows —
`infer_provider_class(name)` — and builds it from `agent.provider`
(`base_url`/`api_version`/`options`), mapping `base_url` onto whichever parameter
that constructor takes (`provider_kwargs`, signature-driven, unknown names
rejected). `provider_catalog()` reports what is importable here plus the install
hint for what is not, which is what the settings dropdown shows.

Frontend: SvelteKit 2 + Svelte 5 runes + TypeScript, Tailwind v4,
shadcn-svelte (vega/lucide), adapter-static SPA. Talks HTTP JSON only via
`src/lib/api/client.ts` — no imports from `src/` (decoupling contract).
Routes: `/`, `/ask`, `/capture`, `/activity`, `/search`, `/settings`, `/p/[...id]`.
Markdown is rendered with `marked` + DOMPurify (never hand-rolled).
Component tests run in Chromium (vitest browser mode).
