# MySharedBrain

<!-- Checks -->
[![CI (Backend)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml)
[![CI (Frontend)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-frontend.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-frontend.yml)
[![Lint](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/lint.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/lint.yml)
[![CodeQL](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/codeql.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/codeql.yml)
[![Conventional Commits](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/commitlint.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/commitlint.yml)

<!-- Delivery -->
[![Docker Build & Push](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/docker.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/docker.yml)
[![Release Please](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/release-please.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/release-please.yml)
[![Tag release image](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/release-image.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/release-image.yml)
[![Dependabot Updates](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/dependabot/dependabot-updates)

### Workflows

Every badge above is one workflow; the jobs are the batches inside it.

| Workflow | Jobs | Runs on |
| -------- | ---- | ------- |
| [CI (Backend)](.github/workflows/ci-backend.yml) | `lint-and-typecheck` (ruff, basedpyright) · `test` (pytest) | `src/**`, `pyproject.toml`, `uv.lock` |
| [CI (Frontend)](.github/workflows/ci-frontend.yml) | `lint-and-typecheck` (svelte-check, prettier, eslint) · `test` (vitest browser) · `build` (adapter-static) | `frontend/**` |
| [Lint](.github/workflows/lint.yml) | `actionlint` · `shell` (shellcheck in run blocks) · `zizmor` · `hadolint` · `bandit` · `dependencies` (pip-audit, pnpm audit) | workflows, Dockerfile, `src/**`, `uv.lock`, `frontend/**`; weekly |
| [CodeQL](.github/workflows/codeql.yml) | `analyze` (python, javascript-typescript; `security-and-quality`) | `src/**`, `frontend/src/**`; weekly |
| [Conventional Commits](.github/workflows/commitlint.yml) | `commits` · `pull-request-title` · `main-commits` (informational) | pull requests; pushes to `main` |
| [Docker Build & Push](.github/workflows/docker.yml) | `prepare` (tags) · `build` (per-arch, native runners) · `merge` (manifest) | `src/**`, `frontend/**`, `Dockerfile` |
| [Release Please](.github/workflows/release-please.yml) | `release-please` — maintains the release PR from conventional commits | pushes to `main` |
| [Tag release image](.github/workflows/release-image.yml) | `tag` — copies the release commit's image to `vX.Y.Z` | published releases |
| [Dependabot Updates](.github/dependabot.yml) | one batch per ecosystem: `uv`, `npm` (frontend), `github-actions`, `docker` | weekly |

An information management system meant for AI. A fully fledged markdown vault
wiki: view it as a wiki in the web UI, CRUD any page, move notes, search by
name or content. One note = one `.md` file, folders = real folders, flat or
nested.

Think of it as a **brain with a librarian**: gather information from it, add
to it, remove from it, edit it — and it gets smarter from the interaction.
The **feedback** function is the critical loop: file a note and the brain
updates itself in the future, either from the information you hand over or
from where you say to get it. In increments the librarian **processes the
capture queue** (reviewed and double-checked) before updating the vault, so
teaching is always safe and never silent. All changes to the vault and the
queue are **audited** (like git). Mutations flow through one audited service
layer, exposed to agents via **MCP**.

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

MCP is how you use the brain: gather information (read, search, browse), add
to it (create, append), edit it (update, patch, frontmatter) and remove from
it (soft-delete, move, restore). `give_feedback` is the critical loop — teach
the brain by filing what it gets wrong, what is missing (with the content or
where to find it), or what to fetch; the librarian applies it later. Asking
with no answer files an automated question the same way, so nothing is lost.
Deployment config (settings, model/MCP/job checks and runs) and capture-queue
moderation stay behind the Settings UI and the librarian's own in-process
tools; they're not exposed to MCP clients.

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
| `give_feedback` | Queue an edit · flag missing info · file a request or question |
| `ask_question` | Ask the librarian; a miss files an automated question |

Capture-queue moderation (`list_capture`, `review_capture`,
`set_capture_status`) and deployment config (`get_settings`,
`update_settings`, `list_model_providers`, `test_model`, `test_mcp_server`,
`run_job`, `list_job_runs`) are not MCP tools — the librarian's own agent
still reaches the capture queue directly, and the Settings UI covers config.

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

A save replaces the whole document — there is no per-field merge between what
you saved and what is still only in the file, so once you save, the seed file
stops mattering until that row is deleted. `GET /api/settings/export` (also
`export_config_yaml()` in Python) returns the effective config — defaults, file
and saved settings all merged — as YAML, with the API key masked: writing that
back out as `brain.yaml` reproduces the same config field for field, so it is
the supported way to turn a saved UI config back into a file you can commit or
hand to another install. An environment override still wins over the re-seeded
file, same as it wins over the database today.

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

`opencode` (alias `opencode-go`) is the OpenCode Zen Go gateway
(`https://opencode.ai/zen/go/v1`, OpenAI-compatible). Empty `base_url` uses that
endpoint; each run sends its own `x-opencode-session` id plus a `mysharedbrain`
user agent, as Zen asks. Pin the session with
`provider.options: {session_id: <stable-id>}` when one conversation must span runs
(`user_agent` overrides the default `mysharedbrain/<version>` agent).

```yaml
agent:
  model: kimi-k2.7-code
  provider: { name: opencode }
  api_key_env: OPENCODE_API_KEY
```

### MCP servers

Remote (`http`/`sse`) servers only — `stdio` is refused because the librarian
has no shell. Each entry takes a `url`, extra `headers`, an `enabled` switch,
and `insecure` (default `false`):

```yaml
mcp_servers:
  - name: lab
    transport: http
    url: https://lab/mcp
    headers: { Authorization: 'Bearer …' }
    enabled: true
    insecure: false
```

`insecure: true` skips TLS certificate verification (self-signed certificates).
Only enable it for a server you trust on a network you trust: without
verification, anyone on the network path can read and modify the traffic,
including headers and tool payloads.

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

### Ask the librarian

The Ask page (`POST /api/request`) is one interactive agent run per question —
the same librarian model, instructions and tools plumbing as a job, but with no
schedule. How it runs lives in the `ask:` config section (Settings → Ask): an
enable switch, its own instructions note, tool/MCP-server restrictions and a
step budget. Off means the page and the endpoint refuse to run. The run answers
from the vault and files capture entries itself (`give_feedback`) when the vault
cannot answer, so a miss lands in the queue for review instead of going silent.

### Shipped schedule

The example schedule is also the **default**: four disabled jobs forming a
capture pipeline plus vault upkeep, with `scheduler.enabled: false`.
`capture-triage` (every 4h) rules on pending entries — approved or rejected,
never applied. `capture-apply` (daily) incorporates the approved ones group by
group and marks them applied. `vault-layout` (Sunday 03:00) owns the layout
template and reshapes notes to match it, never deleting. `vault-audit`
(Saturday 04:00) walks every note and files capture requests, never editing
directly. Each job only gets the tools its stage needs, so the pipeline flows
one way: audit proposes → triage rules → apply incorporates. A fresh install
therefore shows the shapes worth having in Settings → Jobs while running
nothing, and the Settings page says so plainly until you enable a job *and*
the scheduler. A test keeps `brain.example.yaml` and the defaults in step, so
the documentation cannot drift from the behaviour.

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

## Vault administration

The `admin/` section holds markdown the librarian manages the vault by:
`admin/templates/` for page-type templates, `admin/prompts/` for reusable
prompts, and `admin/templates/layout` for the wiki layout new pages follow.
The standing instructions always name these docs (see `admin_instructions`),
so every run reads its template before creating a page and its prompt before
a job. The mappings (`admin.dir`, `layout_template`, per-type `templates`,
named `prompts`) are config, not a settings-page tab — set them in the YAML
file or via `PUT /api/settings` and edit the docs themselves as regular vault
pages.

```yaml
admin:
  dir: admin
  layout_template: admin/templates/layout
  templates: { meeting: admin/templates/meeting }
  prompts: { triage: admin/prompts/triage }
```

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

Queue entries are of kind `edit`, `missing`, `request` or `question` — each one
a note for the brain to update itself from in the future. An `edit` corrects
what the vault gets wrong; a `missing` names a gap and carries the content or
where to find it; a `request` asks the librarian to fetch or do something; a
`question` leaves an open question for future retrieval. The brain is a
self-learning system that requires interaction: no feedback, no learning. Ones
the system files on its own — an unanswered question the librarian could not
resolve — are marked `automated`, so a reviewer can tell machine-filed work
from a person's. Asking with no answer files a `question`; anything a human
queues in the UI stays unmarked.

State is `pending` → `applied` / `approved` / `rejected`, normally through a
review (`POST /api/capture/{id}/review`), which is guarded: an entry can never be
reviewed twice and a race cannot both win. The queue also offers a **State**
dropdown on every entry, resolving or not, which uses the override
`PUT /api/capture/{id}/status` — any state, including back to `pending`, and no
vault write. Overrides are audited as `capture-<state>` with a `restate:` detail,
so a manual state change is never mistaken for a reviewed apply.
