# MySharedBrain: multi-stage image — SvelteKit UI build → backend deps → runtime.
# The backend serves the built UI (./static) and the API from one image.

# Stage 1: build the UI (SvelteKit adapter-static → /app/frontend/build)
FROM node:24-alpine AS frontend-builder

RUN npm install -g pnpm@9

WORKDIR /app/frontend

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

# Stage 2: install backend dependencies
FROM python:3.13-slim AS backend-builder

COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Stage 3: runtime
FROM python:3.13-slim

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# ripgrep powers vault content search (pure-Python fallback if absent)
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY --from=backend-builder /app/.venv /app/.venv
COPY src ./src
COPY --from=frontend-builder /app/frontend/build ./static

ENV VAULT_DIR=/data/vault
# Config lives with the data so it can be mounted (configmap/secret).
ENV BRAIN_CONFIG=/data/brain.yaml
RUN mkdir -p /data/vault && chown -R appuser:appgroup /app /data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["/app/.venv/bin/mysharedbrain"]
