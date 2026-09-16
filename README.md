# MySharedBrain

[![CI Backend](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml)
[![CI Frontend](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-frontend.yml)
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
  audit.py           append-only audit log (like git log)
  db.py              sqlite connection + forward-only migrations
  migrations/        numbered .sql schema files (0001_init.sql, …)
  protocols.py       storage contracts (AuditStore, CaptureStore)
  service.py         the librarian: single audited mutation path
  config.py          Pydantic config: agent, tools, MCP servers, jobs
  agent.py           Pydantic-AI agent built from that config
  tools.py           built-in tools (vault + capture only)
  jobs.py            scheduler: interval/cron runs + history (sqlite)
  api_settings.py    settings REST API (read/write config, run jobs)
  app.py             REST API + serves the UI
  mcp.py             MCP server (mirrors every route)
  db.py              sqlite connection + forward-only migrations
  migrations/        numbered .sql schema files (0001_init.sql, …)
  protocols.py       storage contracts (AuditStore, CaptureStore)
frontend/            SvelteKit UI (Svelte 5 runes + TS, Tailwind 4, shadcn-svelte)
  src/lib/api/       typed HTTP client — the only backend coupling
  src/lib/components shadcn-svelte primitives + app components
Dockerfile           multi-stage: UI build → backend deps → runtime
```

## Frontend

SvelteKit 2 + Svelte 5 (runes) + TypeScript, Tailwind CSS v4, shadcn-svelte
(vega style, lucide icons), `adapter-static` in SPA mode. No SSR: the build
output (`index.html` + hashed `_app/` assets) is served by the FastAPI backend
from `./static` (`build/` locally, `./static` in the image).

```bash
cd frontend
pnpm install
pnpm dev      # UI on :5173, proxying /api + /health to :8000
pnpm test     # unit (node) + component (vitest browser, chromium)
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
| `read_notes` | Batch-read several notes (missing ids reported) |
| `list_notes` | List note ids (prefix filter + pagination) |
| `list_directory` | Direct children of a folder |
| `update_note` | Update note by id |
| `append_note` | Append to a note (prefer over rewrites) |
| `patch_note` | Replace/append a section under a heading |
| `delete_note` | Soft-delete a note to trash |
| `restore_note` | Restore a trashed note |
| `move_note` | Move/rename note |
| `search_notes` | Search names + content (ripgrep) |
| `search_by_tag` | Notes with a frontmatter tag |
| `get_frontmatter` / `set_frontmatter` | Read/merge YAML frontmatter |
| `get_backlinks` / `get_outgoing` | `[[Link]]` graph neighbors |
| `recent_changes` | Latest audited changes, newest first (kind filter, limit/offset) |
| `note_history` | Every interaction with one note + per-kind counts |
| `list_capture` | List queue entries (status filter, limit/offset) |
| `give_feedback` | Queue an edit · flag missing info · file a request or question |
| `review_capture` | Review queue entry: applied/approved/rejected |
| `set_capture_status` | Override a queue entry's state (any state) |
| `ask_question` | Ask the librarian; a miss files an automated question |
| `test_mcp_server` | Check an MCP server connects, and list its tools |
| `test_model` | Check the configured model answers, and how fast |
| `get_settings` | Read the brain config (token masked) |
| `update_settings` | Replace the brain config |
| `run_job` | Run a scheduled job immediately |
| `list_job_runs` | Recent runs of a scheduled job |

## Configuration

One Pydantic config file drives the agent, its tools, the MCP servers and the
scheduled jobs. Copy `brain.example.yaml` to `brain.yaml` (git-ignored) or point
`BRAIN_CONFIG` at a mounted configmap; every value can be overridden from the
environment with the `BRAIN__` prefix and `__` nesting:
```bash
BRAIN__AGENT__MODEL=openai:gpt-4o
BRAIN__AGENT__API_KEY=sk-…      # from a secret, never committed
```

Precedence, lowest to highest: **defaults → seed file → database → environment**.

- The **database** is the store of record: the settings page saves into
  `.brain/brain.db` (one row, one transaction), so there is no file to half-write
  and a read-only mount still works.
- The **seed file** is only ever read. Point `BRAIN_CONFIG` at it (a configmap,
  say) and it applies until you save from the settings page.
- The **environment** always wins, so a container can pin values and inject
  secrets regardless of what was saved.

The page shows which layer is live. To hand control back to the seed file, delete
the stored row: `sqlite3 "$VAULT_DIR/.brain/brain.db" "DELETE FROM settings"`.

### Any provider, any endpoint

`agent.provider` is optional. Empty, the model string decides everything. Fill it
in to point somewhere else — a local server, a gateway, a provider whose SDK wants
different argument names:

```yaml
agent:
  model: llama3.1                      # a bare id is fine with a provider set
  provider:
    name: ollama                       # provider key pydantic-ai resolves
    base_url: http://localhost:11434/v1
```

`base_url` is handed to whichever parameter that provider actually takes —
`base_url` for openai/ollama, `azure_endpoint` for azure, `api_base` for litellm —
read from the constructor's signature, because the SDKs disagree. `api_version`
and an `options` map (by the provider's own argument names, e.g.
`{region: eu-west-1}` for bedrock) cover the rest, and an unknown name is rejected
with the list of what the provider does accept rather than being ignored.

`GET /api/settings/providers` lists what this install can import, so the settings
page offers it as a dropdown and shows a missing SDK with its install hint instead
of failing later. The **Test model** check exercises the real endpoint.

```yaml
agent:
  model: openai:gpt-4o-mini
  api_key_env: OPENAI_API_KEY
  instructions_file: librarian.md   # markdown the librarian may rewrite
scheduler:
  enabled: true
  tick_seconds: 30
jobs:
  - id: capture-triage
    every: 4h                       # or: cron: "0 3 */2 * *"
    instructions: Group and resolve the pending capture queue.
```

The agent runs only the enabled built-in tools (vault notes + capture queue,
nothing else) plus any enabled remote MCP server, so a scheduled run cannot do
anything a human reviewer could not. There is no shell: built-ins touch the vault
and the capture queue, MCP servers are remote (`http`/`sse` only — a local
`stdio` server is refused, since that would be process execution), and the one
`subprocess` in the codebase is ripgrep, called with an argument list and `--`,
never a shell. Each run is recorded in `job_runs` with its
outcome, visible in the UI under Settings → Jobs → History — and every change it
makes is audited under the `librarian` actor as it happens, plus one summary
entry per run (`job-ok` / `job-error` / `job-skipped`). Filter the Activity page
on `librarian` to see everything the agent did on its own.

Librarian runs at `temperature: 0.2` by default — it edits a shared vault, so
careful and repeatable beats creative. Change `agent.temperature` to taste, or set
it to `null` to let the provider decide.

### Watching the scheduler

The scheduler logs what it is doing, at INFO:

```
INFO  mysharedbrain.jobs: scheduler started: ticking every 30s, 3 enabled job(s)
INFO  mysharedbrain.jobs: next run: capture-triage at 2026-09-17T08:00:00+00:00
INFO  mysharedbrain.jobs: tick: 1 job(s) due: capture-triage
INFO  mysharedbrain.jobs: job capture-triage: started
INFO  mysharedbrain.jobs: job capture-triage: ok in 12.4s (3 request(s), 7 tool call(s))
INFO  mysharedbrain.jobs: job capture-triage: next run at 2026-09-17T12:00:00+00:00
```

Failures log the traceback and record an `error` run; a concurrent trigger is a
WARNING and a `skipped` run. Nothing due is DEBUG, so a quiet brain stays quiet.
Set `BRAIN_LOG_LEVEL=DEBUG` for more. `configure_logging()` runs at startup —
without it the root logger has no handler and INFO goes nowhere.

### Shipped schedule

The example schedule is also the **default**: three disabled jobs
(`capture-triage` every 4h, `vault-sweep` cron `0 3 */2 * *`, `source-check`
every 6d) with `scheduler.enabled: false`. A fresh install therefore shows the
shapes worth having in Settings → Jobs while running nothing, and the Settings
page says so plainly until you enable a job *and* the scheduler. A test keeps
`brain.example.yaml` and the defaults in step, so the documentation cannot drift
from the behaviour.

Plus MCP resources (`vault://<id>`, `vault://index`) and prompts
(`ask_librarian`, `file_feedback`).

Add to an MCP client (stdio):

```json
{ "mcpServers": { "mysharedbrain": {
  "command": "uv", "args": ["run", "mysharedbrain", "--mcp"],
  "cwd": "/path/to/mysharedbrain",
  "env": { "VAULT_DIR": "/path/to/vault" }
} } }
```

## REST API

Notes `POST/GET/PUT/DELETE/PATCH /api/notes…` (+ `/move`, `/append`, `/batch`, `/restore`),
`GET /api/browse`, `/api/notes/{id}/{meta,outgoing,backlinks}`, `/api/tags/{tag}`,
`GET /api/search?q=`, `POST /api/feedback`, `GET /api/capture`,
`POST /api/capture/{id}/review`, `POST /api/request`, `GET /api/audit`, `GET /health`.

## Docker

```bash
docker build -t mysharedbrain .
docker run -p 8000:8000 -v mysharedbrain-data:/data/vault mysharedbrain
```

The image builds the UI (node stage) and the backend (uv stage), then serves
both from one process: API under `/api`, UI at `/`.

Images are published to `ghcr.io/hampusadamsson/mysharedbrain` (`sha-<sha>`,
`latest` on `main`).

## Vault layout

```
$VAULT_DIR/
  <note-id>.md        notes, flat or in real folders
  .brain/
    brain.db          sqlite sidecar: audit log + capture queue
                      (WAL mode — brain.db-wal / brain.db-shm alongside)
```

Every note id is validated as a path and then resolved, so a symlink inside the
vault cannot be used to read or write outside it — the vault is the only thing
any actor, agent included, can reach through the API.

Notes themselves are not in the database: a note id is a path, so reading one is
a `stat` (already O(1)) and filename search is a directory walk. The database
holds the sidecar state, and its indexes are chosen from measured query plans
(`src/tests/test_query_plans.py` pins them): the file log filtered by kind and
the two counter summaries are seeks or index-only reads, not scans. `PRAGMA
optimize` runs on connection close so the planner's statistics stay in step with
the log.

## File log

Every interaction with a file is logged with the file it concerns, so a note can
show its own history. Each entry carries the note id plus two levels of
vocabulary: the precise `action` (`read`, `find`, `patch`, `capture-applied`,
`job-ok`, …) and a coarse `kind` used for filtering — `read` · `find` · `write` ·
`move` · `delete` · `capture` · `job` · `other`.

- reads are logged when a note (or a batch) is fetched,
- `find` is logged per note surfaced by a keyword search,
- writes/deletes/moves/captures/agent runs are logged as before, tagged with the
  actor that made them (`api`, `mcp`, `curator`, or `librarian`).

`GET /api/notes/{id}/history?kind=&limit=&offset=` returns the entries, a total,
and per-kind counts (plus first/last sighting). `GET /api/audit?kind=&limit=&offset=`
returns the *same shape* for the whole log, so both views render one shared
component (`InteractionLog.svelte`): counters as filter chips, then the paginated
list. Activity is the whole-log scope, the file view is one note's scope.
Type-ahead search passes `track=false` so browsing the dropdown does not fill the
log with keystrokes. Counters always cover the whole scope, so a kind filter
changes the rows shown, never the numbers next to the filters.

Remote MCP servers are declared in the same file and contribute tools to any job
that allows them. Both kinds of connection are checked the same way — on save,
and on demand per row:

- **MCP servers**: connect and list tools (`POST /api/settings/mcp/test`).
- **The model**: ask it for a one-word answer (`POST /api/settings/model/test`),
  which is the cheapest real proof that the provider, the model string and the
  token all work.

Each returns `{name, ok, detail, tools}` — one shape, so one component renders
the feedback: a spinner while it runs, then a green `ok · …` or a red
`failed · …` with the error. Checks are bounded (10s for a server, 20s for the
model) and never raise. Credentials are scrubbed from the message: providers
quote the key back ("Incorrect API key provided: sk-…"), so a token cannot leak
into the UI or the log that way.

## Capture kinds

Queue entries are of kind `edit`, `missing`, `request` or `question`. Ones the
system files on its own — an unanswered question the librarian could not resolve
— are marked `automated`, so a reviewer can tell machine-filed work from a
person's. Asking with no answer files a `question`; anything a human queues in
the UI stays unmarked.

State is `pending` → `applied` / `approved` / `rejected`, normally through a
review (`POST /api/capture/{id}/review`), which is guarded: an entry can never be
reviewed twice and a race cannot both win. The queue also offers a **State**
dropdown on every entry, resolving or not, which uses the override
`PUT /api/capture/{id}/status` — any state, including back to `pending`, and no
vault write. Overrides are audited as `capture-<state>` with a `restate:` detail,
so a manual state change is never mistaken for a reviewed apply.
