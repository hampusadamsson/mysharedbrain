# MySharedBrain

[![CI (Backend)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-backend.yml)
[![CI (Frontend)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-frontend.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/ci-frontend.yml)
[![Lint](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/lint.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/lint.yml)
[![CodeQL](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/codeql.yml/badge.svg?branch=main&event=push)](https://github.com/hampusadamsson/mysharedbrain/actions/workflows/codeql.yml)

<!-- 944x1113 source; width is set here so GitHub does not scale it past the fold -->
<p align="center">
  <img src="1789799392416.png" alt="A badger reading a book" width="320">
</p>

A markdown vault with a librarian — an information system built for AI to read
and write, where the writing is checked before it counts.

## What it is

Notes are `.md` files in ordinary folders, flat or nested. A librarian agent
reads them, answers questions from them, and files what it cannot answer. A web
UI covers both sides: pages you can edit, and a queue of what the librarian wants
to change in them.

## What problem it solves

An AI answer is plausible before it is true. The usual failure is **slop**:
fluent, confident text that says little and cannot be traced or corrected. It
reads fine in a chat window and it reads fine in a wiki, which is the danger —
once it is written down, nobody can tell it apart from something verified.

MySharedBrain puts the vault between the model and the reader:

- **Answers come from pages.** A claim either has a page or it does not; there is
  no third option where the model sounds sure.
- **A miss is filed, not invented.** The librarian queues it (a `question`
  entry) instead of filling the gap, so the unknown stays visible.
- **Nothing lands unreviewed.** The capture queue is the gate: entries are
  `edit`, `missing`, `request` or `question`, and a reviewer applies, approves or
  rejects each one before it touches the vault.
- **Every change is attributed.** The audit log records the actor — `api`,
  `mcp`, `curator` or `librarian` — so a machine edit is never mistaken for
  yours.
- **The house style is plain, and it is written down.** The librarian's
  instructions are a markdown page you own, so the style is a thing you edit
  rather than a default you hope for — and the reviewer applies the same
  standard to every queued entry: awkward, flowery, vague, unnecessary or
  illogical wording, and the always-flag AI-isms — em dashes, semicolons,
  arrows, inline bullets, "not X, it's Y", passive voice, imperative titles,
  slogans.

The test for any of it is one question: *could this be rewritten significantly
better?* If yes, it belongs in the queue, not in the vault.

## Quick start

```bash
git clone https://github.com/hampusadamsson/mysharedbrain && cd mysharedbrain
uv sync                       # uv fetches Python 3.13
cp .env.example .env          # VAULT_DIR, defaults to ./vault
uv run mysharedbrain          # API + docs on http://localhost:8000
```

The vault works without a model; the librarian does not:

```bash
export OPENAI_API_KEY=sk-…    # any provider, see Configuration
curl -sX POST localhost:8000/api/request -H 'Content-Type: application/json' \
  -d '{"question":"what runs on elitedesk?"}'
```

Give it to an agent over MCP (stdio):

```json
{ "mcpServers": { "mysharedbrain": {
  "command": "uv", "args": ["run", "mysharedbrain", "--mcp"],
  "cwd": "/path/to/mysharedbrain",
  "env": { "VAULT_DIR": "/path/to/vault" }
} } }
```

Or run the image, which serves API and UI from one process:

```bash
docker run -p 8000:8000 -v mysharedbrain-data:/data/vault \
  -e OPENAI_API_KEY=… ghcr.io/hampusadamsson/mysharedbrain:latest
```

## How to operate

| Where | What you do there |
| ----- | ----------------- |
| **Pages** | Read and edit the vault; a page shows its own history |
| **Ask** | One question → one librarian run. A miss files a `question` |
| **Capture** | Review the queue: apply, approve or reject, or set any state |
| **Activity** | The whole audit log, filterable by kind; filter on `librarian` to see what it did alone |
| **Settings** | Agent, Ask, Jobs, Tools, MCP servers, Templates — plus export/import of the effective config |

Jobs run the same librarian on a schedule with narrower tools. The shipped
schedule is four *disabled* examples forming a pipeline: `capture-triage` rules
on pending entries, `capture-apply` incorporates the approved ones,
`vault-layout` reshapes notes to the layout template, `vault-audit` re-checks
sources and files requests. Every run is recorded (Settings → Jobs → History)
and audited.

Its reach is bounded on purpose: no shell, no local (`stdio`) MCP servers, no
multi-user auth. The tools it may use are vault notes, the capture queue, and
whichever remote MCP servers you enable — never more than a human reviewer has.

## MCP tools

| Tool | Description |
| ---- | ----------- |
| `create_note` · `read_note` · `read_notes` | Create, read, batch-read |
| `update_note` · `append_note` · `patch_note` | Rewrite, append, replace a section under a heading |
| `delete_note` · `restore_note` · `move_note` | Soft-delete to trash, restore, move |
| `list_notes` · `list_directory` | List ids, or one folder's children |
| `search_notes` · `search_by_tag` | Search names and content, or by frontmatter tag |
| `get_frontmatter` · `set_frontmatter` | Read or merge YAML frontmatter |
| `get_backlinks` · `get_outgoing` | `[[Link]]` neighbours |
| `recent_changes` · `note_history` | Audited changes, whole vault or one note |
| `give_feedback` | Queue an edit, missing info, a request or a question |
| `ask_question` | Ask the librarian; a miss files a `question` |

Plus resources (`vault://<id>`, `vault://index`) and prompts (`ask_librarian`,
`file_feedback`). Configuration stays out of MCP: it lives in the UI.

## Configuration

One config document drives the agent, its tools, MCP servers and jobs. Copy
`brain.example.yaml` to `brain.yaml`, or point `BRAIN_CONFIG` at a mounted file.
Environment overrides use `BRAIN__` with `__` nesting, and always win:

```bash
BRAIN__AGENT__MODEL=openai:gpt-4o
BRAIN__AGENT__API_KEY=sk-…     # from a secret, never committed
```

Precedence, lowest to highest: defaults → seed file → saved settings →
environment. The settings page saves into `VAULT_DIR/.brain/brain.db`, so the
seed file stops mattering once you save; delete that row to hand control back.
`GET /api/settings/export` prints the effective config as YAML with the token
masked.

```yaml
agent:
  model: openai:gpt-4o-mini
  api_key_env: OPENAI_API_KEY
  instructions_file: librarian.md   # markdown the librarian may rewrite
  temperature: 0.2
ask:
  enabled: true
  timeout_seconds: 60
scheduler:
  enabled: true
  tick_seconds: 30
jobs:
  - id: capture-triage
    every: 4h                       # or: cron: "0 3 */2 * *"
    instructions: Group and resolve the pending capture queue.
```

Any provider, any endpoint: `agent.provider` is optional — leave it empty and
the model string decides everything; fill in `name`, `base_url`, `api_version`
and `options` to point at a local server or a gateway.
`GET /api/settings/providers` lists what this install can import. Remote MCP
servers are declared in the same file (`http`/`sse`, with `headers`, `enabled`
and an `insecure` switch that skips TLS verification — only for a network you
trust).

## Where things live

The vault is `VAULT_DIR`: notes as `.md` files, and beside them
`.brain/brain.db` (SQLite, WAL) holding the audit log, the capture queue, job
runs and saved settings. Back the directory up and you have everything. Note ids
are validated as paths and resolved, so a symlink inside the vault cannot reach
outside it.

## API

Interactive docs at **`/docs`** (and `/redoc`, `/openapi.json`); MCP tools mirror
every route. Notes `POST/GET/PUT/DELETE/PATCH /api/notes…` (+ `/move`, `/append`,
`/batch`, `/restore`), `GET /api/notes/{id}/history`, `GET /api/browse`,
`GET /api/search?q=`, `POST /api/feedback`, `GET /api/capture`,
`POST /api/capture/{id}/review`, `PUT /api/capture/{id}/status`,
`POST /api/request`, `GET /api/audit`, `GET|PUT /api/settings…`, `GET /health`.

## Deploy and develop

Images publish to `ghcr.io/hampusadamsson/mysharedbrain`: `sha-<commit>` and
`latest` on every `main` build, plus `vX.Y.Z` when a release is published.
Mount one volume at `/data/vault`, set the key from a secret, point the ingress
at port 8000; the probe is `GET /health`.

```bash
uv sync && uv run pytest src/tests/ -q          # backend (TDD; main stays green)
uv run ruff check src/ && uv run basedpyright
cd frontend && pnpm dev                         # UI on :5173, proxying /api
pnpm check && pnpm lint && pnpm test && pnpm build
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):
Release Please reads them to cut versions, and CI vets them on every pull
request.

## License

MIT — see [LICENSE](LICENSE).
