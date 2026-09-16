# UI migration plan: vanilla JS → SvelteKit (static build)

> **Status: implemented** (2026-09-16). All six steps shipped; the deployed
> image serves the Svelte UI. Kept as the record of the migration.
>
> Deviations from the plan as written:
> - `svelte.config.js` is not used — the static adapter is configured in
>   `vite.config.ts` (the `sv` scaffold passes options to the vite plugin).
> - Component tests run in Chromium via vitest browser mode, so CI installs
>   Playwright browsers (`pnpm exec playwright install --with-deps chromium`).
> - `docker.yml` was rewritten to build each architecture on a **native**
>   runner (amd64 + `ubuntu-24.04-arm`) and merge digests with
>   `docker buildx imagetools create`. The single-job QEMU build took 38+ min
>   for the UI stage; native runners cut it to ~1 min.

Reference implementation: `golfkompis` frontend (same patterns, proven in prod).
Goal: keep the decoupling contract (UI talks HTTP JSON only), keep one runtime
image, keep unique URLs — replace the 700-line no-build `app.js` with a typed
component app.

## Target stack (mirror golfkompis)

| Concern | Choice |
| ------- | ------ |
| Framework | SvelteKit 2, Svelte 5, **runes mode enforced** |
| Language | TypeScript + `svelte-check` |
| Output | `@sveltejs/adapter-static` with `fallback: 'index.html'` (SPA mode, no SSR) |
| Styling | Tailwind CSS v4 (`@tailwindcss/vite`) |
| Components | **shadcn-svelte** (vega style, lucide icons, bits-ui, tailwind-variants) |
| Markdown | `marked` + `dompurify` (kills the homegrown renderer; link allowlist kept) |
| Package manager | pnpm (workspace files + `.npmrc`) |
| Lint/format | eslint (flat config, `eslint-plugin-svelte`, `typescript-eslint`) + prettier (`-svelte`, `-tailwindcss` plugins) |
| Tests | vitest component tests; browser mode (playwright) same as golfkompis, or jsdom to start |

## Route map (URLs preserved — zero API changes)

| Current | SvelteKit |
| ------- | --------- |
| `/` (empty state) | `routes/+page.svelte` |
| `/ask` | `routes/ask/+page.svelte` |
| `/capture` | `routes/capture/+page.svelte` |
| `/activity` | `routes/activity/+page.svelte` |
| `/p/<id…>` (note/folder) | `routes/p/[...id]/+page.svelte` |
| manual `history.pushState`/`popstate` | SvelteKit router (`Link`, `goto`) — delete the hand-rolled router |

Deep links keep working: server returns the SPA fallback, client router boots.

## Component breakdown (shadcn-svelte primitives)

- `TopBar.svelte` (custom) — search with results dropdown, Create button
- `Sidebar.svelte` (custom) + `PageTree.svelte` (custom, collapsible, pagination
  — port the current tree logic into a Svelte store)
- `NoteView.svelte` / `NoteEdit.svelte` — view (marked+DOMPurify) / edit
  (inline rename field, save/rename/conflict error — port current behavior)
- Modals → **Dialog**: create page, move, delete, apply-feedback (editor dialog)
- Capture cards → **Card** + **Badge** (status/kind lozenges) + **Tabs** (status filter)
- Buttons/inputs/selects/textarea → **Button / Input / Select / Textarea**
- Toasts → **Sonner** (replaces the inline error box where it fits better)
- Audit feed → custom list + avatar

Confluence look stays: vega neutral base, brand blue via CSS vars.

## API client

- `src/lib/api/client.ts` — thin fetch wrapper (current `api` object, typed)
- Types generated from the live OpenAPI spec: `openapi-typescript` against
  `/openapi.json` (regen step documented; the parity test keeps API==MCP)
- `vite.config.ts` dev proxy: `/api`, `/health` → `http://localhost:8000`
  (same as golfkompis, minus auth/db routes)

## Backend change (small, golfkompis pattern)

`app.py`: replace `/static` mount + SPA fallback with:

```python
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
if _STATIC_DIR.is_dir():
    app.mount("/_app", StaticFiles(directory=_STATIC_DIR / "_app"))
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        candidate = _STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
```

Local dev unaffected (no `static/` dir → pure API server + vite dev server).
OpenAPI/SPA-fallback tests updated to the new pattern.

## Build & image (Dockerfile rewrite)

```dockerfile
# Stage 1: frontend (new)
FROM node:24-alpine AS frontend-builder
RUN npm install -g pnpm@9
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build            # → frontend/build

# Stage 2: backend deps (unchanged: uv sync)
# Stage 3: runtime (python:3.13-slim)
#   COPY --from=frontend-builder /app/frontend/build ./static   # instead of COPY frontend
```

- `.dockerignore`: add `frontend/node_modules`, `frontend/.svelte-kit`, `frontend/build`, `frontend/.env*`
- `docker.yml` CI: paths already include `frontend/**`; add pnpm-store cache
- Keep multi-arch QEMU/Buildx; GHCR tags unchanged

## CI (new `ci-frontend.yml`, copy golfkompis shape)

- pnpm/action-setup + node 24 + cache (`frontend/pnpm-lock.yaml`)
- Jobs: `lint-and-typecheck` (`pnpm check`, `pnpm lint`) and `build` (+ `pnpm test` once component tests exist)
- Paths filter: `frontend/**`, workflow file

## Steps (each ends green & pushed)

1. **Scaffold** — `sv create` (minimal, TS, pnpm) in `frontend/`; `sv add tailwindcss`;
   `shadcn-svelte init` (vega/lucide/neutral); add Dialog/Button/Input/etc.;
   vite dev proxy; `pnpm build` works. Commit (old UI still live).
2. **Shell + navigation** — TopBar, Sidebar, route pages as stubs; URLs match current ones.
3. **Core: notes** — PageTree, NoteView (marked+DOMPurify), NoteEdit with inline
   rename + conflict handling; search dropdown. Port the headless-harness
   scenarios into vitest component tests.
4. **Capture + Ask + Activity** — queue cards w/ apply-dialog, ask+feedback, audit feed.
5. **Cutover** — backend serving swap (pattern above), Dockerfile stages,
   `ci-frontend.yml`, delete old `app.js`/`styles.css`/`index.html`. Single
   release: image bump → chart tag bump → ArgoCD.
6. **Verify live** — deep links, tree pagination, mobile drawer (pure CSS),
   apply-dialog flow, OpenAPI docs untouched, badges green.

## Risks / decisions

- **Moving targets**: shadcn-svelte + Tailwind 4 release fast — pin like
  golfkompis does, run `pnpm up` deliberately.
- **Vitest browser mode** needs playwright browsers in CI (~1 min install);
  acceptable (golfkompis does it), but jsdom start is allowed if we want CI lean.
- **Bundle**: `_app/immutable` assets are hashed & immutable — served from
  image; no CDN concerns at this scale.
- Old no-build UI is deleted in step 5, not kept side-by-side (single source of
  truth; rollback = previous image tag).
