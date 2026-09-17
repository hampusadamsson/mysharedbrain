"""Packaging guard: runtime imports must be runtime dependencies.

The image installs with ``uv sync --no-dev``. A dependency that lives only in
the dev group therefore works in tests and locally but explodes in the
container — this happened for real: ``pydantic_ai/mcp.py`` imports ``httpx`` at
module level, and the app imports ``pydantic_ai.mcp`` lazily when MCP servers
are configured, so every scheduled/agent job failed with
``ModuleNotFoundError: No module named 'httpx'`` while the HTTP API stayed up.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: Import the app performs at runtime -> distribution that must ship in the image.
RUNTIME_IMPORTS = {
    "httpx": "pydantic_ai.mcp (module-level import)",
    "fastmcp": "MCP server",
    "pydantic-ai-slim": "agent",
    "croniter": "job schedules",
    "pyyaml": "config + frontmatter",
    "fastapi": "API",
    "uvicorn": "server",
}


def _project() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _names(requirements: list[str]) -> set[str]:
    """Normalise ``pkg>=1.0`` / ``pkg[extra]>=1.0`` to ``pkg``."""
    names: set[str] = set()
    for req in requirements:
        name = req.split(";")[0].split("[")[0].strip()
        for sep in (">=", "==", "~=", "<=", ">", "<", "!="):
            name = name.split(sep)[0]
        names.add(name.strip().lower())
    return names


def test_runtime_dependencies_cover_runtime_imports() -> None:
    runtime = _names(_project()["project"]["dependencies"])  # type: ignore[index]
    missing = {pkg: why for pkg, why in RUNTIME_IMPORTS.items() if pkg not in runtime}
    assert not missing, f"runtime deps missing (image uses --no-dev): {missing}"


def test_httpx_is_not_dev_only() -> None:
    """httpx was dev-only once; agent/MCP job runs need it in the image."""
    project = _project()
    runtime = _names(project["project"]["dependencies"])  # type: ignore[index]
    dev = _names(project.get("dependency-groups", {}).get("dev", []))  # type: ignore[union-attr]
    assert "httpx" in runtime, "httpx must be a runtime dependency"
    assert "httpx" not in dev, "httpx is runtime; drop the duplicate dev entry"
