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

## Workflows

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

## What it is

**A markdown vault with a librarian.** You ask it something through the web UI
or an MCP client; it answers from the vault, and when it cannot answer, the miss
becomes queue work instead of a dead end. Notes are ordinary `.md` files in
ordinary folders — flat or nested — so the vault is readable, greppable and
backup-able without this application.

The whole point is the loop: the brain gets better because what it got wrong,
lacked or should fetch is written down, reviewed, and then filed into the vault.

- **Markdown vault** — CRUD, move, search by name and content (ripgrep), YAML
  frontmatter, tags, `[[wiki links]]` with backlinks, soft-delete to trash.
- **Librarian agent** — answers questions from the vault and files what it
  cannot answer. Configurable model, provider, instructions and tools.
- **Feedback queue (capture)** — `edit`, `missing`, `request` and `question`
  entries: a correction, a gap, a to-fetch, an open question. Reviewed
  (`applied` / `approved` / `rejected`) before anything touches the vault.
- **Scheduled jobs** — the same agent with narrower tools: triage the queue,
  apply what was approved, reshape notes to the layout template, audit sources.
- **Audit log** — every read, write, move, delete, review and job run, with the
  actor that made it (`api`, `mcp`, `curator`, `librarian`). Per-note history.
- **Web UI** — pages, ask, capture queue, activity, and settings for the agent,
  jobs, tools and MCP servers. Responsive; no build step needed to view.
- **Settings as config** — one config document driving agent, tools, MCP servers
  and jobs, editable in the UI and overridable from the environment.

Deliberately out of scope: no shell, no `stdio` MCP servers (that would be
process execution), and no multi-user auth. The vault directory is the boundary —
the agent can reach exactly what a human reviewer could.

## Quick start

### Locally (uv)

You need [uv](https://docs.astral.sh/uv/); it fetches Python 3.13 for you.

```bash
git clone https://github.com/hampusadamsson/mysharedbrain
cd mysharedbrain
cp .env.example .env        # VAULT_DIR, defaults to ./vault
uv sync
uv run mysharedbrain        # API on http://localhost:8000 (interactive docs at /docs)
```

`uv run mysharedbrain` serves the API, and the UI if `./static` exists (that is
what the container has; for the UI with hot reload see [Develop](#develop)).

Point it at a model — the agent needs one, the vault does not:

```bash
export OPENAI_API_KEY=sk-…                       # or any provider, see Configuration
curl -sX POST localhost:8000/api/notes -H 'Content-Type: application/json' \
  -d '{"id":"projects/homelab","content":"# Homelab\n\nk3s runs on elitedesk.\n"}'
curl -sX POST localhost:8000/api/request -H 'Content-Type: application/json' \
  -d '{"question":"what runs on elitedesk?"}'
```

### With MCP (how agents use it)

```json
{ "mcpServers": { "mysharedbrain": {
  "command": "uv", "args": ["run", "mysharedbrain", "--mcp"],
  "cwd": "/path/to/mysharedbrain",
  "env": { "VAULT_DIR": "/path/to/vault" }
} } }
```

### In a container

```bash
docker run -p 8000:8000 -v mysharedbrain-data:/data/vault \
  ghcr.io/hampusadamsson/mysharedbrain:latest
```

Configuration lives outside the image: mount `VAULT_DIR` and inject the API key
(`-e OPENAI_API_KEY=…`), or bake a seed config with `BRAIN_CONFIG`.

## How to operate

### The UI

| Page | What it is for |
| ---- | -------------- |
| **Pages** | The vault: a page tree, markdown view, editor with inline rename, move/delete, properties and history |
| **Ask** | One question → one librarian run, with a spinner and a timeout you set in Settings · Ask |
| **Capture** | The feedback queue: review pending entries, set any state, see what the agent filed |
| **Activity** | The whole audit log, filterable by kind |
| **Settings** | Agent, Ask, Jobs, Tools, MCP servers, Templates + export/import of the effective config |

### The feedback loop

`give_feedback` — from the UI form, an MCP client, or the agent itself — queues
an entry. Kinds:

| Kind | Meaning |
| ---- | ------- |
| `edit` | The vault gets something wrong; carry the correction |
| `missing` | A gap; carry the content or where to find it |
| `request` | Fetch or do something |
| `question` | An open question, for future retrieval (an unanswered `ask` files one) |

Entries the system files on its own are marked `automated`, so a reviewer can
tell machine-filed work from a person's. State is `pending` → `applied` /
`approved` / `rejected`, normally through a review
(`POST /api/capture/{id}/review`), which is guarded: an entry can never be
reviewed twice and a race cannot both win. The queue also offers a **State**
dropdown on every entry, resolving or not — the override
(`PUT /api/capture/{id}/status`) sets any state, including back to `pending`,
and writes nothing to the vault. Overrides are audited as `capture-<state>` with
a `restate:` detail, so a manual change is never mistaken for a reviewed apply.

### The librarian, on a schedule

Jobs run the same agent with narrower tools, so a scheduled run cannot do more
than a human reviewer could. The shipped schedule is four **disabled** jobs that
form a pipeline (`scheduler.enabled: false` too):

| Job | When | What it does |
| --- | ---- | ------------ |
| `capture-triage` | every 4h | Rules on pending entries — approved or rejected, never applied |
| `capture-apply` | daily | Incorporates approved entries group by group, marking them applied |
| `vault-layout` | Sunday 03:00 | Owns the layout template and reshapes notes to match, never deleting |
| `vault-audit` | Saturday 04:00 | Walks every note and files capture requests, never editing |

Each run is recorded in `job_runs` (Settings → Jobs → History, or
`GET /api/settings/jobs/{id}/runs`) and audited as it happens, plus one summary
entry per run (`job-ok` / `job-error` / `job-skipped`). Filter Activity on
`librarian` to see everything the agent did on its own.

The scheduler logs what it is doing at INFO:

```
INFO  mysharedbrain.jobs: scheduler started: ticking every 30s, 3 enabled job(s)
INFO  mysharedbrain.jobs: tick: 1 job(s) due: capture-triage
INFO  mysharedbrain.jobs: job capture-triage: ok in 12.4s (3 request(s), 7 tool call(s))
```

A failure logs the traceback and records an `error` run; a concurrent trigger is
a `skipped` run. Set `BRAIN_LOG_LEVEL=DEBUG` for more.

### Checking the wiring

Both kinds of connection are checked the same way — on save, and on demand:

- **MCP servers** — connect and list the tools they offer
  (`POST /api/settings/mcp/test`).
- **The model** — ask for a one-word answer (`POST /api/settings/model/test`),
  the cheapest proof that provider, model string and token all work.

Each returns `{name, ok, detail, tools}`, so one component renders the result: a
spinner, then a green `ok · …` or a red `failed · …`. Checks are bounded (10s for
a server, 20s for the model) and never raise. Credentials are scrubbed from the
message — providers quote the key back, and it must not reach the UI or a log.

### History and audit

Every interaction is logged with the note it concerns and two levels of
vocabulary: the precise `action` (`read`, `find`, `patch`, `capture-applied`,
`job-ok`, …) and a coarse `kind` for filtering — `read` · `find` · `write` ·
`move` · `delete` · `capture` · `job` · `other`. Reads are logged when a note (or
batch) is fetched; `find` per note surfaced by a search.

`GET /api/notes/{id}/history?kind=&limit=&offset=` returns entries, a total and
per-kind counts; `GET /api/audit…` returns the same shape for the whole log, so
both views render one component: counters as filter chips, then the list.
Counters always cover the whole scope, so filtering changes the rows, never the
numbers.

### Vault administration

The `admin/` section holds the markdown the librarian manages the vault *by*:
`admin/templates/` for page-type templates, `admin/prompts/` for reusable
prompts, and `admin/templates/layout` for the layout new pages follow. Every run
reads its template before creating a page and its prompt before a job. The
mappings are config, not files:

```yaml
admin:
  dir: admin
  layout_template: admin/templates/layout
  templates: { meeting: admin/templates/meeting }
  prompts: { triage: admin/prompts/triage }
```

### Where state lives

Notes are `.md` files under `VAULT_DIR` — not in a database. Sidecar state lives
beside them in `VAULT_DIR/.brain/brain.db` (SQLite, WAL): the audit log, the
capture queue, job runs and the saved settings row. Back up the directory and you
have backed up everything.

Note ids are validated as paths and then resolved, so a symlink inside the vault
cannot be used to read or write outside it. Notes stay out of the database on
purpose: a note id *is* a path, so reading one is a `stat` and filename search is
a directory walk. The database's indexes are pinned by measured query plans
(`src/tests/test_query_plans.py`), and `PRAGMA optimize` runs on connection close.

## Connect an agent over MCP

MCP is how an agent uses the brain: gather information (read, search, browse),
add to it (create, append), edit it (update, patch, frontmatter) and remove from
it (soft-delete, move, restore). `give_feedback` is the critical loop — teach the
brain by filing what it got wrong, what is missing, or what to fetch; the
librarian applies it later. Deployment config and capture moderation are
deliberately *not* MCP tools: they stay behind the Settings UI, and the
librarian's own in-process tools.

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

Plus MCP resources (`vault://<id>`, `vault://index`) and prompts
(`ask_librarian`, `file_feedback`).

## Configuration

One config document drives the agent, its tools, the MCP servers and the jobs.
Copy `brain.example.yaml` to `brain.yaml`, or point `BRAIN_CONFIG` at a mounted
configmap. Any value can be overridden from the environment with `BRAIN__` and
`__` nesting:

```bash
BRAIN__AGENT__MODEL=openai:gpt-4o
BRAIN__AGENT__API_KEY=sk-…      # from a secret, never committed
```

Precedence, lowest to highest: **defaults → seed file → database → environment**.

- The **database** is the store of record: the settings page saves into
  `.brain/brain.db` (one row, one transaction), so there is no file to
  half-write and a read-only config mount still works.
- The **seed file** is only ever read. It applies until you save from the
  settings page.
- The **environment** always wins, so a container can pin values and inject
  secrets regardless of what was saved.

The settings page shows which layer is live. To hand control back to the seed
file, delete the stored row:
`sqlite3 "$VAULT_DIR/.brain/brain.db" "DELETE FROM settings"`.

A save replaces the whole document. `GET /api/settings/export` returns the
effective config — defaults, file and saved settings merged — as YAML with the
token masked, and writing that back as `brain.yaml` reproduces it field for
field: the supported way to turn a UI config into a file you can commit.

### Any provider, any endpoint

`agent.provider` is optional. Empty, the model string decides everything; fill it
in to point elsewhere — a local server, a gateway, a provider whose SDK wants
different argument names:

```yaml
agent:
  model: llama3.1                      # a bare id is fine with a provider set
  provider:
    name: ollama                       # provider key pydantic-ai resolves
    base_url: http://localhost:11434/v1
```

`base_url` is handed to whichever parameter that provider actually takes
(`base_url` for openai/ollama, `azure_endpoint` for azure, `api_base` for
litellm) — read from the constructor's signature, because the SDKs disagree.
`api_version` and an `options` map (`{region: eu-west-1}` for bedrock) cover the
rest, and an unknown name is rejected with the list of what the provider accepts
rather than ignored. `GET /api/settings/providers` lists what this install can
import, so the UI offers a dropdown and shows a missing SDK with its install hint.

`opencode` (alias `opencode-go`) is the OpenCode Zen Go gateway
(`https://opencode.ai/zen/go/v1`, OpenAI-compatible): empty `base_url` uses that
endpoint, and each run sends its own `x-opencode-session` id plus a
`mysharedbrain` user agent. Pin the session with
`provider.options: {session_id: <stable-id>}` when one conversation must span
runs.

### MCP servers

Remote (`http`/`sse`) servers only — `stdio` is refused, because the librarian
has no shell. Each entry takes a `url`, extra `headers`, an `enabled` switch and
`insecure` (default `false`):

```yaml
mcp_servers:
  - name: lab
    transport: http
    url: https://lab/mcp
    headers: { Authorization: 'Bearer …' }
    enabled: true
    insecure: false
```

`insecure: true` skips TLS certificate verification (self-signed certs). Only for
a server and network you trust: without verification anyone on the path can read
and modify the traffic, headers and tool payloads included.

### A working config, end to end

```yaml
agent:
  model: openai:gpt-4o-mini
  api_key_env: OPENAI_API_KEY
  instructions_file: librarian.md   # markdown the librarian may rewrite
  temperature: 0.2                  # careful and repeatable; null lets the provider decide
ask:
  enabled: true
  timeout_seconds: 60               # the Ask page spins for at most this long
scheduler:
  enabled: true
  tick_seconds: 30
jobs:
  - id: capture-triage
    every: 4h                       # or: cron: "0 3 */2 * *"
    instructions: Group and resolve the pending capture queue.
```

The agent runs only the enabled built-in tools (vault notes + capture queue)
plus any enabled remote MCP server. There is no shell: the one `subprocess` in
the codebase is ripgrep, called with an argument list and `--`, never a shell.

## API

Interactive docs: **`/docs`** (and `/redoc`, `/openapi.json`) — MCP tools mirror
every route.

Notes `POST/GET/PUT/DELETE/PATCH /api/notes…` (+ `/move`, `/append`, `/batch`,
`/restore`), `GET /api/browse`, `/api/notes/{id}/{meta,outgoing,backlinks,history}`,
`/api/tags/{tag}`, `GET /api/search?q=`, `POST /api/feedback`, `GET /api/capture`,
`POST /api/capture/{id}/review`, `PUT /api/capture/{id}/status`,
`POST /api/request`, `GET /api/audit`, `GET|PUT /api/settings…`, `GET /health`.

## Deploy

The image is multi-stage: the UI is built (node), the backend is resolved (uv),
then one process serves both — API under `/api`, UI at `/`.

```bash
docker build -t mysharedbrain .
docker run -p 8000:8000 -v mysharedbrain-data:/data/vault \
  -e OPENAI_API_KEY=… mysharedbrain
```

Published to `ghcr.io/hampusadamsson/mysharedbrain` as `sha-<commit>` (every
`main` build), `latest` (same build), and `vX.Y.Z` once a release is published
(the release commit's digest is copied, not rebuilt — the bytes CI tested are the
bytes you pull). On Kubernetes, mount one volume at `/data/vault`, set the API
key from a secret, and point the ingress at port 8000; the health probe is
`GET /health`. `VAULT_DIR` defaults to `/data/vault` in the image, and
`BRAIN_CONFIG` to `/data/brain.yaml` for a mounted seed config.

Releases are cut by merging the `chore: release X.Y.Z` pull request that Release
Please maintains from conventional commits — see the workflow table at the top
for what each automation does.

## Develop

```bash
# backend
uv sync
uv run pytest src/tests/ -q
uv run ruff check src/ && uv run ruff format --check src/
uv run basedpyright

# frontend (SvelteKit UI)
cd frontend
pnpm install
pnpm dev        # :5173, proxying /api + /health to :8000
pnpm check && pnpm lint && pnpm test && pnpm build
```

TDD is the rule: write or extend the test first, and `main` stays green. The
frontend is SvelteKit 2 (Svelte 5 runes, TypeScript, Tailwind 4, shadcn-svelte)
built with `adapter-static` in SPA mode — no SSR: the build output is served by
the same FastAPI process. Component tests run in a real browser (vitest browser
mode, chromium).

Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `docs:` …): the vetting workflow enforces it, Release Please
reads it to pick the next version, and `AGENTS.md` documents the convention for
agents working in this repo.

## License

MIT — see [LICENSE](LICENSE).
