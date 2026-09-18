"""Settings API: read/write the brain config and drive scheduled jobs.

The config file is the single source of truth, so the UI edits the *whole*
document (``PUT /api/settings``) rather than poking individual jobs — one
validated write, one atomic file replace, then the scheduler reloads. The
secret token is write-only: responses mask it, and sending the mask back keeps
the stored value.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, cast

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError

from mysharedbrain.agent import check_mcp_server, check_model, provider_catalog
from mysharedbrain.config import (
    MASK,
    AgentConfig,
    BrainConfig,
    BrainConfigDocument,
    MCPServerConfig,
    config_path,
    config_source,
    export_config_yaml,
    load_config,
    parse_config,
    parse_config_yaml,
)
from mysharedbrain.jobs import JobStore, get_scheduler
from mysharedbrain.service import vault_root
from mysharedbrain.settings_store import SettingsStore
from mysharedbrain.tools import TOOLS

router = APIRouter(prefix="/api", tags=["settings"])


class JobStatusOut(BaseModel):
    id: str
    name: str
    enabled: bool
    schedule: str
    next_run: str = ""
    last_run: str = ""
    last_status: str = ""


class ToolOut(BaseModel):
    name: str
    description: str
    enabled: bool


class SettingsOut(BaseModel):
    config: dict[str, Any]
    jobs: list[JobStatusOut]
    tools: list[ToolOut]
    config_path: str
    config_source: str
    api_key_env: str
    api_key_configured: bool


class SettingsIn(BaseModel):
    config: dict[str, Any]


class SettingsImportIn(BaseModel):
    yaml: str


class ProviderOut(BaseModel):
    """One selectable provider, and what it needs to be configured."""

    name: str
    available: bool
    url_param: str = ""
    api_version_param: str = ""
    hint: str = ""


class ProvidersOut(BaseModel):
    providers: list[ProviderOut]
    current: str
    model: str


class CheckOut(BaseModel):
    """A connection check: green/red plus one line of feedback.

    One shape for both checks (MCP server and model provider) so the UI renders
    them with a single component. ``tools`` is what a server offers; a model
    offers none.
    """

    name: str
    ok: bool
    detail: str
    tools: list[str] = []


class JobRunOut(BaseModel):
    id: int
    job_id: str
    started_at: str
    finished_at: str
    status: str
    detail: str


class JobRunsOut(BaseModel):
    runs: list[JobRunOut]


def _current() -> BrainConfig:
    """Fresh load of every settings layer (env > database > seed file)."""
    return load_config()


def _tools_view(cfg: BrainConfigDocument) -> list[ToolOut]:
    return [
        ToolOut(
            name=spec.name,
            description=spec.description,
            enabled=cfg.tools[spec.name].enabled if spec.name in cfg.tools else True,
        )
        for spec in TOOLS.values()
    ]


def _snapshot(cfg: BrainConfigDocument) -> SettingsOut:
    scheduler = get_scheduler()
    scheduler.reload(cfg)
    return SettingsOut(
        config=cfg.redacted(),
        jobs=[JobStatusOut(**row) for row in scheduler.status()],
        tools=_tools_view(cfg),
        # The seed file is shown for context; the document itself is in the
        # database, which is what config_source reports.
        config_path=str(config_path()),
        config_source=config_source(),
        api_key_env=cfg.agent.api_key_env,
        api_key_configured=bool(cfg.agent.api_key) or bool(_env_token(cfg)),
    )


def _env_token(cfg: BrainConfigDocument) -> str:
    return os.environ.get(cfg.agent.api_key_env, "")


@router.get("/settings", response_model=SettingsOut, summary="Read the brain config")
def get_settings() -> SettingsOut:
    return _snapshot(_current())


@router.get(
    "/settings/export",
    response_class=PlainTextResponse,
    summary="Effective config as YAML, redacted — usable as a seed file",
)
def export_settings() -> str:
    # Redacted: this is the download-and-share path, and a leaked API key in
    # a shared seed file is exactly the mistake redaction exists to prevent.
    return export_config_yaml(_current(), redact=True)


@router.put("/settings", response_model=SettingsOut, summary="Replace the brain config")
def update_settings(payload: SettingsIn) -> SettingsOut:
    current = _current()
    data = dict(payload.config)
    agent = data.get("agent")
    if isinstance(agent, dict):
        agent_dict = cast("dict[str, object]", agent)
        if agent_dict.get("api_key") == MASK:
            agent_dict["api_key"] = current.agent.api_key  # keep the stored secret
    try:
        cfg = parse_config(data)
    except ValidationError as exc:
        raise ValueError(f"invalid config: {exc.errors()[0]['msg']}") from exc
    _check_tool_names(cfg)
    # Saved into the vault database, never the seed file: a read-only configmap
    # can stay read-only, and half-written YAML is not a failure mode.
    SettingsStore(vault_root()).save(cfg.model_dump(mode="json"))
    return _snapshot(cfg)


@router.put(
    "/settings/import",
    response_model=SettingsOut,
    summary="Replace the brain config from pasted/uploaded YAML",
)
def import_settings(payload: SettingsImportIn) -> SettingsOut:
    """The Templates/Import tab's paste-a-file path: same YAML shape as
    ``export_config_yaml`` produces, so a config exported from one install
    round-trips into another exactly — and it goes through the same
    validation and masked-token handling as :func:`update_settings`.
    """
    try:
        data = parse_config_yaml(payload.yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid yaml: {exc}") from exc
    return update_settings(SettingsIn(config=data))


def _check_tool_names(cfg: BrainConfigDocument) -> None:
    """Reject unknown tool names here: config cannot know the registry."""
    known = set(TOOLS)
    unknown = set(cfg.tools) - known
    if unknown:
        raise ValueError(f"unknown tool(s): {sorted(unknown)}")
    for job in cfg.jobs:
        job_unknown = set(job.tools or ()) - known
        if job_unknown:
            raise ValueError(f"job {job.id!r}: unknown tool(s) {sorted(job_unknown)}")


@router.get(
    "/settings/providers",
    response_model=ProvidersOut,
    summary="Model providers this install can reach, and what they need",
)
def list_providers() -> ProvidersOut:
    """The provider catalog, filtered to what is actually installed.

    A name whose SDK is missing is listed with the install hint rather than
    hidden, so the settings form can show it as unavailable instead of failing on
    save. ``current`` is the provider in effect (from the config, or the model
    string's prefix).
    """
    cfg = _current()
    model_id = cfg.agent.model.strip()
    current = cfg.agent.provider.name or (
        model_id.split(":", 1)[0] if ":" in model_id else ""
    )
    return ProvidersOut(
        providers=[ProviderOut(**asdict(info)) for info in provider_catalog()],
        current=current,
        model=model_id,
    )


@router.post(
    "/settings/mcp/test",
    response_model=CheckOut,
    summary="Check that an MCP server connects (lists its tools)",
)
async def test_mcp_server(server: MCPServerConfig) -> CheckOut:
    """Try the given server config and report tools or the failure.

    Takes the server inline rather than by name, so the settings form can check
    an edited (not yet saved) row too.
    """
    return CheckOut(**asdict(await check_mcp_server(server)))


@router.post(
    "/settings/model/test",
    response_model=CheckOut,
    summary="Check that the configured model answers",
)
async def test_model(agent: AgentConfig) -> CheckOut:
    """Ask the configured model for a one-word answer.

    Same deal as the MCP check: a real round trip, so a green line means the
    provider, the model string and the token all work. Takes the agent config
    inline (an unsaved edit can be checked), resolving the mask to the stored
    token the way a save does.
    """
    if agent.api_key == MASK:
        agent = agent.model_copy(update={"api_key": _current().agent.api_key})
    document = BrainConfigDocument(agent=agent)
    return CheckOut(**asdict(await check_model(document)))


@router.post(
    "/settings/jobs/{job_id}/run",
    response_model=JobRunOut,
    summary="Run a scheduled job now",
)
async def run_job(job_id: str) -> JobRunOut:
    scheduler = get_scheduler()
    scheduler.reload(_current())
    try:
        run = await scheduler.run_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JobRunOut(**run.__dict__)


@router.get(
    "/settings/jobs/{job_id}/runs",
    response_model=JobRunsOut,
    summary="Recent runs of a scheduled job",
)
def job_runs(job_id: str, limit: int = 20) -> JobRunsOut:
    runs = JobStore(vault_root()).recent(job_id, limit=limit)
    return JobRunsOut(runs=[JobRunOut(**run.__dict__) for run in runs])
