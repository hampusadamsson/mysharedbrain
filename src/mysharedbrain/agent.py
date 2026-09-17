"""The librarian agent: a Pydantic-AI agent over the configured tools.

One agent is built per run: instructions come from markdown (vault note +
inline config), tools are the enabled built-ins (vault/capture only) plus any
enabled remote MCP servers. Nothing else — the agent has no shell, no network
beyond the MCP servers you declare.

The model is whatever the config says (``openai:gpt-4o``, ``anthropic:…``);
the token comes from the environment variable named in the config, so a
container can inject it from a secret.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.exceptions import UserError
from pydantic_ai.models import infer_model
from pydantic_ai.settings import ModelSettings

from mysharedbrain.config import BrainConfigDocument, JobSpec, MCPServerConfig
from mysharedbrain.service import Librarian
from mysharedbrain.tools import build_tools

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastmcp.client import Client
    from pydantic_ai.mcp import MCPToolset
    from pydantic_ai.models import Model
    from pydantic_ai.run import AgentRunResult


@dataclass(frozen=True)
class AgentOutcome:
    """What a run produced: the model's final text plus usage counts."""

    output: str
    requests: int
    tool_calls: int


#: How long an MCP connect check may take before it is called a failure.
MCP_CHECK_TIMEOUT = 10.0

#: How long a model round trip may take before it is called a failure.
MODEL_CHECK_TIMEOUT = 20.0

#: Provider keys pydantic-ai resolves, as candidates. What actually shows up is
#: filtered at runtime — a name whose SDK is not installed is reported as
#: unavailable with the install hint, and the list only needs a name added here
#: when the library gains a provider we care about.
#: OpenCode Zen Go (https://opencode.ai/zen/go/v1): OpenAI-compatible gateway.
#: Not a pydantic-ai provider name, so it is aliased onto OpenAI below.
OPENCODE_BASE_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_PROVIDER_NAMES: tuple[str, ...] = ("opencode", "opencode-go")

PROVIDER_CANDIDATES: tuple[str, ...] = (
    "openai",
    "openai-chat",
    "openai-responses",
    "opencode",
    "opencode-go",
    "azure",
    "azure-responses",
    "anthropic",
    "google",
    "google-cloud",
    "bedrock",
    "mistral",
    "groq",
    "cohere",
    "deepseek",
    "openrouter",
    "together",
    "fireworks",
    "cerebras",
    "sambanova",
    "nebius",
    "crusoe",
    "moonshotai",
    "alibaba",
    "zai",
    "xai",
    "github",
    "github-copilot",
    "heroku",
    "huggingface",
    "litellm",
    "ollama",
    "vllm",
    "vercel",
    "ovhcloud",
    "snowflake",
    "sentence-transformers",
    "voyageai",
)

#: Constructor parameters that mean "the endpoint", most specific first: the
#: SDKs disagree, and this is how ``provider.base_url`` finds the right one.
_URL_PARAMS: tuple[str, ...] = (
    "azure_endpoint",
    "api_base",
    "base_url",
    "endpoint",
    "url",
)


@dataclass(frozen=True)
class ProviderInfo:
    """One selectable provider, and what it needs — for the settings UI."""

    name: str
    available: bool
    url_param: str = ""
    api_version_param: str = ""
    hint: str = ""


def _is_opencode(name: str) -> bool:
    """OpenCode Zen Go alias (`opencode` / `opencode-go`)."""
    return name.strip().lower() in OPENCODE_PROVIDER_NAMES


def _user_agent() -> str:
    """Own user agent: Zen asks clients not to use a generic SDK name."""
    try:
        from importlib.metadata import version

        return f"mysharedbrain/{version('mysharedbrain')}"
    except Exception:
        return "mysharedbrain/0.1.0"


def _provider_class(name: str) -> type[Any]:
    """The provider class pydantic-ai would use (lazily imported by it)."""
    from pydantic_ai.providers import infer_provider_class

    if _is_opencode(name):
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIProvider
    return infer_provider_class(name)


def _provider_params(cls: type[Any]) -> set[str]:
    return set(inspect.signature(cls.__init__).parameters) - {"self"}


@lru_cache(maxsize=1)
def provider_catalog() -> tuple[ProviderInfo, ...]:
    """Every candidate provider, marked available or not (cached: it imports)."""
    out: list[ProviderInfo] = []
    for name in PROVIDER_CANDIDATES:
        try:
            cls = _provider_class(name)
        except ImportError as exc:  # SDK not installed — say how to get it
            out.append(ProviderInfo(name=name, available=False, hint=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - unknown name in the list
            out.append(ProviderInfo(name=name, available=False, hint=str(exc)))
            continue
        params = _provider_params(cls)
        out.append(
            ProviderInfo(
                name=name,
                available=True,
                url_param=next((p for p in _URL_PARAMS if p in params), ""),
                api_version_param="api_version" if "api_version" in params else "",
            )
        )
    return tuple(sorted(out, key=lambda info: (not info.available, info.name)))


def model_string(cfg: BrainConfigDocument) -> str:
    """The model string to infer, with the provider prefix when it is implied."""
    model_id = cfg.agent.model.strip()
    provider_name = cfg.agent.provider.name.strip()
    if provider_name and ":" not in model_id:
        return f"{provider_name}:{model_id}"
    return model_id


def provider_kwargs(cls: type[Any], cfg: BrainConfigDocument) -> dict[str, Any]:
    """Translate the provider config into that provider's own argument names.

    Anything the constructor does not accept is an error listing what it does:
    a silently dropped ``base_url`` would look like it worked.
    """
    params = _provider_params(cls)
    wanted = cfg.agent.provider
    kwargs: dict[str, Any] = {}
    problems: list[str] = []

    if wanted.base_url:
        url_param = next((p for p in _URL_PARAMS if p in params), "")
        if not url_param:
            problems.append(f"base_url (this provider takes none of {_URL_PARAMS})")
        else:
            kwargs[url_param] = wanted.base_url
    if wanted.api_version:
        if "api_version" in params:
            kwargs["api_version"] = wanted.api_version
        else:
            problems.append("api_version")
    token = cfg.agent.api_key or os.environ.get(cfg.agent.api_key_env, "")
    if token and "api_key" in params:
        kwargs["api_key"] = token
    for key, value in wanted.options.items():
        if key in params:
            kwargs[key] = value
        else:
            problems.append(key)

    if problems:
        accepted = ", ".join(sorted(params))
        raise ValueError(
            f"provider {cls.__name__} does not accept {', '.join(problems)}; "
            f"it takes: {accepted}"
        )
    return kwargs


def _opencode_provider(cfg: BrainConfigDocument) -> tuple[Any, str]:
    """OpenAI client for Zen Go: default endpoint + session headers.

    Zen asks clients to send a stable ``x-opencode-session`` per conversation
    (routing/prompt caching) and their own user agent. One provider instance
    serves one agent run, so a fresh id per build is one session per run;
    ``provider.options.session_id`` pins it when a stable id is wanted.
    Chat completions cover most Go models; that is the inference path used.
    """
    from openai import AsyncOpenAI
    from pydantic_ai.providers.openai import OpenAIProvider

    wanted = cfg.agent.provider
    if wanted.api_version:
        raise ValueError("provider OpenAIProvider does not accept api_version")
    unknown = sorted(k for k in wanted.options if k not in ("session_id", "user_agent"))
    if unknown:
        raise ValueError(
            f"provider OpenAIProvider does not accept {', '.join(unknown)}; "
            "it takes: base_url, api_key, session_id, user_agent"
        )
    base_url = wanted.base_url.strip() or OPENCODE_BASE_URL
    token = cfg.agent.api_key or os.environ.get(cfg.agent.api_key_env, "")
    session_id = wanted.options.get("session_id", "").strip() or uuid.uuid4().hex
    user_agent = wanted.options.get("user_agent", "").strip() or _user_agent()
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=token or "api-key-not-set",
        default_headers={"x-opencode-session": session_id, "User-Agent": user_agent},
    )
    return OpenAIProvider(openai_client=client), session_id


def build_model(cfg: BrainConfigDocument) -> Model:
    """The model to run: any provider, any endpoint, from the config.

    With no provider block this is just ``infer_model(model_string)`` — the
    simple path is unchanged. With one, the provider is constructed from the
    config (endpoint, api version, extra options) and the model string is
    resolved through it.
    """
    _resolve_api_key(cfg)
    model_id = model_string(cfg)
    provider_name = cfg.agent.provider.name.strip()
    if not provider_name and ":" not in model_id:
        return infer_model(model_id)  # known model names such as "test"
    if not provider_name:
        provider_name = model_id.split(":", 1)[0]
    if _is_opencode(provider_name):
        provider, _session = _opencode_provider(cfg)
        bare = model_id.split(":", 1)[1] if ":" in model_id else model_id
        return infer_model(f"openai-chat:{bare}", provider_factory=lambda _n: provider)
    cls = _provider_class(provider_name)
    provider = cls(**provider_kwargs(cls, cfg))
    return infer_model(model_id, provider_factory=lambda _name: provider)


@dataclass(frozen=True)
class ConnectionCheck:
    """Result of trying to reach something: a green/red line for the settings UI.

    One shape for both checks — MCP servers and the model provider — so the UI
    renders them with one component. ``tools`` is what a server offers; it is
    empty for a model, which offers none.
    """

    name: str
    ok: bool
    detail: str
    tools: list[str]


def mcp_transport(server: MCPServerConfig) -> Any:
    """fastmcp transport for a server config — shared by toolsets and checks.

    Remote only: there is no stdio branch, so nothing here can spawn a process.
    ``insecure`` disables TLS certificate verification (self-signed certs);
    verification stays on unless it is explicitly set.
    """
    from fastmcp.client.transports import SSETransport, StreamableHttpTransport

    headers = server.headers or None
    verify = False if server.insecure else None
    if server.transport == "sse":
        return SSETransport(server.url, headers=headers, verify=verify)
    return StreamableHttpTransport(server.url, headers=headers, verify=verify)


def mcp_client(server: MCPServerConfig) -> Client[Any]:
    """A ready-to-connect fastmcp client for one server."""
    from fastmcp.client import Client

    return Client(mcp_transport(server), name=server.name or None)


async def check_mcp_server(
    server: MCPServerConfig,
    *,
    client_factory: Callable[[MCPServerConfig], Client[Any]] | None = None,
    timeout: float = MCP_CHECK_TIMEOUT,
) -> ConnectionCheck:
    """Connect to ``server`` and list its tools. Never raises.

    Bounded by ``timeout`` so a black-holed endpoint cannot hang a request, and
    the error is returned rather than raised, because "can I reach this?" is
    exactly the question being asked. Remote transports only — a check connects
    to a service, it never starts a process.

    ``client_factory`` is the seam tests use to hand in an in-process server
    instead of a real socket.
    """
    client = (client_factory or mcp_client)(server)
    secrets = [value for value in server.headers.values() if value]
    try:
        async with asyncio.timeout(timeout):
            async with client:
                tools = await client.list_tools()
    except TimeoutError:
        return ConnectionCheck(
            name=server.name,
            ok=False,
            detail=f"no response within {timeout:g}s",
            tools=[],
        )
    except Exception as exc:  # refused, bad handshake, dead command, …
        return ConnectionCheck(
            name=server.name,
            ok=False,
            detail=_redact(f"{type(exc).__name__}: {exc}", secrets),
            tools=[],
        )
    names = [tool.name for tool in tools]
    return ConnectionCheck(
        name=server.name,
        ok=True,
        detail=f"{len(names)} tool{'' if len(names) == 1 else 's'}",
        tools=names,
    )


def _redact(text: str, secrets: Iterable[str]) -> str:
    """Never echo a credential back to the UI.

    Provider errors quote what they were given — a bad key comes back as
    "Incorrect API key provided: sk-…" — so a check detail has to be scrubbed
    before it is stored or shown. Short values are ignored: replacing a two
    character env var would mangle the message.
    """
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def _model_secrets(cfg: BrainConfigDocument) -> list[str]:
    env_key = cfg.agent.api_key_env
    return [cfg.agent.api_key, os.environ.get(env_key, "") if env_key else ""]


async def ping_model(model: Model) -> str:
    """One tiny round trip to a model — the cheapest real proof it answers."""
    agent = Agent(
        model,
        instructions="Reply with the single word: ok. Nothing else.",
        name="connection-check",
    )
    result: AgentRunResult[str] = await agent.run(
        "ping", usage_limits=UsageLimits(request_limit=1)
    )
    return str(result.output).strip()


async def check_model(
    cfg: BrainConfigDocument,
    *,
    run: Callable[[Model], Awaitable[str]] | None = None,
    timeout: float = MODEL_CHECK_TIMEOUT,
) -> ConnectionCheck:
    """Ask the configured model for a one-word answer. Never raises.

    Mirrors :func:`check_mcp_server`: actually reach the thing and do its
    smallest operation, so a green line means "this works", not "this parses".
    That costs one request and a handful of tokens, which is the price of a
    check that cannot lie; a bad model string or a missing token is caught on the
    way in, with the provider's own message.

    ``run`` is the test seam (hand in a fake instead of a real provider).
    """
    name = cfg.agent.model
    _resolve_api_key(cfg)
    secrets = _model_secrets(cfg)
    try:
        model = build_model(cfg)
    except Exception as exc:  # unknown provider, missing SDK, bad option, no token
        return ConnectionCheck(
            name=name,
            ok=False,
            detail=_redact(f"{type(exc).__name__}: {exc}", secrets),
            tools=[],
        )
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            answer = await (run or ping_model)(model)
    except TimeoutError:
        return ConnectionCheck(
            name=name, ok=False, detail=f"no response within {timeout:g}s", tools=[]
        )
    except Exception as exc:
        return ConnectionCheck(
            name=name,
            ok=False,
            detail=_redact(f"{type(exc).__name__}: {exc}", secrets),
            tools=[],
        )
    took = (time.perf_counter() - started) * 1000
    return ConnectionCheck(
        name=name,
        ok=True,
        detail=_redact(f"answered in {took:.0f} ms: {answer[:40]}", secrets),
        tools=[],
    )


def _resolve_api_key(cfg: BrainConfigDocument) -> None:
    """Expose a literal token through the configured env var (env wins)."""
    agent = cfg.agent
    if agent.api_key and agent.api_key_env and not os.environ.get(agent.api_key_env):
        os.environ[agent.api_key_env] = agent.api_key


def admin_instructions(cfg: BrainConfigDocument) -> str:
    """Where the vault's admin docs live: templates, prompts, layout.

    Always present, so the librarian manages the vault by these docs — page
    types get their template, new pages follow the layout, reusable prompts
    are read from their notes. Missing notes are fine: the librarian reads
    them with its tools and creates what does not exist yet.
    """
    admin = cfg.admin
    lines = [
        f"Vault administration lives under `{admin.dir}/`.",
        f"New pages follow the wiki layout in `{admin.layout_template}`.",
        f"Page-type templates live under `{admin.dir}/templates/`.",
        f"Reusable prompts live under `{admin.dir}/prompts/`.",
    ]
    for name, ref in sorted(admin.templates.items()):
        lines.append(f"Page type `{name}` uses the template in `{ref}`.")
    for name, ref in sorted(admin.prompts.items()):
        lines.append(f"Prompt `{name}` is the markdown in `{ref}`.")
    return "\n".join(lines)


def load_instructions(cfg: BrainConfigDocument, lib: Librarian) -> str:
    """Standing vault instructions: note markdown (if present) + inline text.

    The note is a normal vault file, so the librarian can rewrite its own
    directions in a scheduled job — that is the intended workflow. The admin
    section (templates, prompts, layout) is always appended, so the librarian
    manages the vault by those docs.
    """
    parts: list[str] = []
    note_id = cfg.agent.instructions_file.strip()
    if note_id:
        # Missing instructions note is fine: inline text still applies.
        with contextlib.suppress(Exception):
            parts.append(lib.read_note(note_id).content.strip())
    if cfg.agent.instructions.strip():
        parts.append(cfg.agent.instructions.strip())
    parts.append(admin_instructions(cfg))
    return "\n\n".join(p for p in parts if p)


def build_mcp_toolsets(
    cfg: BrainConfigDocument, names: list[str] | None = None
) -> list[MCPToolset]:
    """Enabled MCP servers as Pydantic-AI toolsets, optionally restricted."""
    from pydantic_ai.mcp import MCPToolset

    return [
        MCPToolset(mcp_client(server), id=server.name)
        for server in cfg.mcp_servers
        if server.enabled and (names is None or server.name in names)
    ]


def build_agent(
    cfg: BrainConfigDocument,
    lib: Librarian,
    job: JobSpec | None = None,
    model: Model | None = None,
) -> Agent[None, str]:
    """Agent for one run: job-scoped tools, toolsets and instructions.

    ``model`` overrides the configured model — tests pass a ``TestModel`` so a
    full run can be exercised without credentials.
    """
    _resolve_api_key(cfg)
    enabled = {name: spec.enabled for name, spec in cfg.tools.items()}
    only = job.tools if job is not None else None
    builtin = build_tools(lib, enabled, only)
    toolsets = build_mcp_toolsets(cfg, job.mcp_servers if job is not None else None)
    settings = ModelSettings()
    if cfg.agent.temperature is not None:
        settings["temperature"] = cfg.agent.temperature
    if model is None:
        try:
            model = build_model(cfg)
        except UserError as exc:
            # e.g. the provider's token is unset — surface it as a config problem
            # so the run history says exactly what to fix.
            raise ValueError(f"cannot use model {cfg.agent.model!r}: {exc}") from exc
    instructions = load_instructions(cfg, lib) or (
        "You are the librarian for a shared markdown vault. Use only the "
        "provided tools; keep notes coherent and audit every change."
    )
    return Agent(
        model,
        instructions=instructions,
        tools=builtin,
        toolsets=toolsets,
        model_settings=settings,
        name=f"librarian:{job.id}" if job else "librarian",
    )


def prompt_for(cfg: BrainConfigDocument, job: JobSpec, lib: Librarian) -> str:
    """The user prompt for a job: its note markdown (if any) + inline prompt."""
    parts: list[str] = []
    if job.instructions_file:
        try:
            parts.append(lib.read_note(job.instructions_file).content.strip())
        except Exception:
            parts.append(f"(instructions note {job.instructions_file!r} not found)")
    if job.instructions.strip():
        parts.append(job.instructions.strip())
    if not parts:
        parts.append(job.description.strip() or f"Run the scheduled job {job.id!r}.")
    return "\n\n".join(p for p in parts if p)


async def run_agent(
    cfg: BrainConfigDocument,
    lib: Librarian,
    prompt: str,
    job: JobSpec | None = None,
    model: Model | None = None,
) -> AgentOutcome:
    """Build the agent for ``job`` and run ``prompt`` to completion."""
    agent = build_agent(cfg, lib, job, model)
    max_steps = job.max_steps if job and job.max_steps else cfg.agent.max_steps
    result: AgentRunResult[str] = await agent.run(
        prompt, usage_limits=UsageLimits(request_limit=max_steps)
    )
    usage = result.usage
    return AgentOutcome(
        output=str(result.output),
        requests=int(usage.requests),
        tool_calls=int(usage.tool_calls),
    )


__all__ = [
    "MCP_CHECK_TIMEOUT",
    "MODEL_CHECK_TIMEOUT",
    "OPENCODE_BASE_URL",
    "OPENCODE_PROVIDER_NAMES",
    "PROVIDER_CANDIDATES",
    "AgentOutcome",
    "ConnectionCheck",
    "ProviderInfo",
    "admin_instructions",
    "build_agent",
    "build_mcp_toolsets",
    "build_model",
    "check_mcp_server",
    "check_model",
    "load_instructions",
    "mcp_client",
    "mcp_transport",
    "model_string",
    "ping_model",
    "prompt_for",
    "provider_catalog",
    "provider_kwargs",
    "run_agent",
]
