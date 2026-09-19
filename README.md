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

**Context.** An agent can be excellent at the work and still fail, because what
it was given is outdated, incomplete or simply gone. People fare no better: the
document is two years old, the note no longer matches reality, and nobody knows
which page is current. Capability is not the bottleneck — context is.

MySharedBrain maintains a wiki that holds that context:

- **Automated update.** A librarian agent reads and writes the vault, so
  documents get corrected instead of rotting and gaps get filed instead of
  filled with guesses.
- **Context management.** Every entry is a page, every change is reviewed and
  attributed, and what the vault cannot answer stays visible as a queued
  question.
- **One context, many readers.** Built-in MCP, REST API and a web UI read and
  write the same vault, so agents and people work from one source instead of
  each keeping a private copy that drifts.

It is built to manage shared context for the many: several agents and humans on
the same facts, where correcting something once corrects it for everyone — and
where machine-written text is plausible before it is true, which is why nothing
lands unreviewed.

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

Two interfaces over the same vault: **REST** for anything HTTP, **MCP** for
agents. Every MCP tool maps to a route, so a client can reach the vault either
way. The reverse has deliberate exceptions, listed below: configuration and
queue moderation stay HTTP/UI-only, because an agent that could rewrite its own
settings or approve its own queue entries would be checking its own work.

- **REST docs:** `/docs` on a running instance — Swagger UI generated from the
  app, so it is never out of date — plus `/redoc` and `/openapi.json`.
- **MCP:** stdio (`uv run mysharedbrain --mcp`), with tools, resources
  (`vault://<id>`, `vault://index`) and prompts (`ask_librarian`,
  `file_feedback`).

| Task | REST | MCP |
| ---- | ---- | --- |
| Check it is up | `GET /health` | — |
| List pages | `GET /api/notes` (prefix, limit, offset) | `list_notes` |
| Read a page / several | `GET /api/notes/{id}`, `POST /api/notes/batch` | `read_note`, `read_notes` |
| Create a page | `POST /api/notes` | `create_note` |
| Replace a page | `PUT /api/notes/{id}` | `update_note` |
| Append | `POST /api/notes/{id}/append` | `append_note` |
| Replace a section | `PATCH /api/notes/{id}` | `patch_note` |
| Delete / restore | `DELETE /api/notes/{id}`, `POST …/restore` | `delete_note`, `restore_note` |
| Move or rename | `POST /api/notes/{id}/move` | `move_note` |
| Browse a folder | `GET /api/browse?prefix=` | `list_directory` |
| Search names + content | `GET /api/search?q=` | `search_notes` |
| Search by tag | `GET /api/tags/{tag}` | `search_by_tag` |
| Read / merge frontmatter | `GET`, `PUT /api/notes/{id}/meta` | `get_frontmatter`, `set_frontmatter` |
| Links in / out | `GET …/outgoing`, `GET …/backlinks` | `get_outgoing`, `get_backlinks` |
| One page's history | `GET /api/notes/{id}/history` | `note_history` |
| Recent changes | `GET /api/audit` (kind, limit, offset) | `recent_changes` |
| File feedback | `POST /api/feedback` | `give_feedback` |
| Ask the librarian | `POST /api/request` | `ask_question` |
| Review the queue | `GET /api/capture`, `POST …/review`, `PUT …/status` | — (UI, or the librarian's own tools) |
| Settings, checks, jobs | `GET`/`PUT /api/settings`, `/export`, `/import`, `/providers`, `/model/test`, `/mcp/test`, `/jobs/{id}/run`, `/jobs/{id}/runs` | — (UI) |

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
