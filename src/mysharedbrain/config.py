"""Brain configuration: one Pydantic model for agent, tools, MCP and jobs.

Single source of truth, loaded from YAML (``$BRAIN_CONFIG``, default
``brain.yaml``) with environment override on top — so a container can ship a
committed file and inject secrets/config via configmap or env:

    BRAIN__AGENT__MODEL=openai:gpt-4o
    BRAIN__AGENT__API_KEY=sk-…

Precedence: defaults < YAML file < environment. Writes go through
:func:`save_config` (atomic replace), which is how the settings UI persists
changes. Secrets are never returned by the API — :meth:`BrainConfig.redacted`
blanks them.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from mysharedbrain.db import vault_root
from mysharedbrain.settings_store import SettingsStore

DEFAULT_CONFIG_FILE = Path("brain.yaml")
MASK = "********"

DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(value: str) -> int:
    """``"4h"``/``"90m"``/``"2d"`` → seconds. Raises ``ValueError`` otherwise."""
    match = DURATION_RE.match(value.strip().lower())
    if not match:
        raise ValueError(
            f"invalid duration {value!r} (expected e.g. '30m', '4h', '2d')"
        )
    amount, unit = match.groups()
    return int(amount) * _UNIT_SECONDS[unit]


class ProviderConfig(BaseModel):
    """How to reach the model provider, for anything that is not the default.

    Left empty, the model string decides everything (``openai:gpt-4o`` → OpenAI).
    Set ``name`` and usually ``base_url`` for a self-hosted endpoint, a gateway or
    a provider whose SDK wants different names for the same thing — the mapping to
    the provider's own parameters is done in :mod:`mysharedbrain.agent` from its
    constructor signature, so nothing here is guessed.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    """Provider key pydantic-ai knows, e.g. ``openai``, ``ollama``, ``litellm``,
    ``azure``. Empty = take it from the model string's prefix."""

    base_url: str = ""
    """Custom endpoint. Handed to whichever parameter the provider takes
    (``base_url``, ``azure_endpoint``, ``api_base``, …)."""

    api_version: str = ""
    """Required by some providers (Azure OpenAI, for one)."""

    options: dict[str, str] = Field(default_factory=dict)
    """Anything else the provider's constructor needs, by its own argument name
    (``{"azure_endpoint": …}``, ``{"region": …}``). Unknown names are rejected
    with the list of what the provider accepts, rather than ignored."""

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        name = value.strip().lower()
        if name and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            raise ValueError(f"invalid provider name: {value!r}")
        return name

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str) -> str:
        url = value.strip()
        if url and not url.startswith(("http://", "https://")):
            raise ValueError(
                f"base_url must start with http:// or https://, got {value!r}"
            )
        return url


class AgentConfig(BaseModel):
    """Model selection, credentials and the librarian's standing instructions."""

    model_config = ConfigDict(extra="forbid")

    model: str = "openai:gpt-4o-mini"
    """Pydantic-AI model string, e.g. ``openai:gpt-4o``. With a provider name set,
    a bare model id (``gpt-4o``) is enough."""

    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    """Where to reach that model; empty = the model string's provider."""

    api_key: str = ""
    """Literal token. Prefer :attr:`api_key_env`; masked in API responses."""

    api_key_env: str = "OPENAI_API_KEY"
    """Environment variable holding the token (configmap/secret in containers)."""

    instructions_file: str = "librarian.md"
    """Vault note holding the general vault instructions (markdown)."""

    instructions: str = ""
    """Inline markdown, appended after :attr:`instructions_file`."""

    max_steps: int = Field(default=20, ge=1, le=200)

    temperature: float | None = Field(default=0.2, ge=0.0, le=2.0)
    """Default 0.2: the agent edits a shared vault, so answers should be careful
    and repeatable rather than creative. ``null`` defers to the provider's own
    default — useful for providers that reject anything above 1.0."""


def _check_note_ref(value: str) -> str:
    """A vault note id as used by config refs (instructions, templates, …).

    Same safety shape as the vault itself: relative, no ``..``, no hidden
    segments, no control characters — so a ref can never escape the vault.
    """
    text = value.strip().replace("\\", "/")
    if not text:
        raise ValueError("note ref must not be empty")
    if text.startswith("/"):
        raise ValueError(f"absolute paths are not allowed: {value!r}")
    parts = text.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"unsafe path segment in: {value!r}")
    if any(p.startswith(".") for p in parts):
        raise ValueError(f"hidden segments are reserved: {value!r}")
    if any(ord(c) < 32 for c in text):
        raise ValueError(f"control characters are not allowed: {value!r}")
    return text


def _check_slug(value: str) -> str:
    slug = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        raise ValueError(f"invalid name: {value!r} (use a slug like 'meeting')")
    return slug


class AdminConfig(BaseModel):
    """Vault administration: templates, prompts and the wiki layout.

    All markdown, all in the vault: ``dir`` is the section holding the docs
    the librarian manages the vault by (``<dir>/templates/`` for page types,
    ``<dir>/prompts/`` for reusable prompts). ``templates`` maps a page type
    slug to its template note, ``prompts`` a prompt name to its prompt note.
    """

    model_config = ConfigDict(extra="forbid")

    dir: str = "admin"
    """Vault section for admin docs (templates, prompts, layout)."""

    layout_template: str = "admin/templates/layout"
    """Template note for the wiki layout new pages follow (no ``.md`` suffix)."""

    templates: dict[str, str] = Field(default_factory=dict)
    """Page type slug → template note, e.g. ``{meeting: admin/templates/meeting}``."""

    prompts: dict[str, str] = Field(default_factory=dict)
    """Prompt name → prompt note, e.g. ``{triage: admin/prompts/triage}``."""

    @field_validator("dir")
    @classmethod
    def _check_dir(cls, value: str) -> str:
        return _check_note_ref(value)

    @field_validator("layout_template")
    @classmethod
    def _check_layout(cls, value: str) -> str:
        return _check_note_ref(value)

    @field_validator("templates", "prompts", mode="before")
    @classmethod
    def _check_mappings(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        mapping = cast("dict[object, object]", value)
        checked: dict[str, str] = {}
        for raw_key, raw_ref in mapping.items():
            checked[_check_slug(str(raw_key))] = _check_note_ref(str(raw_ref))
        return checked


class ToolConfig(BaseModel):
    """Per-tool switch. Unknown names are rejected against the registry."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class MCPServerConfig(BaseModel):
    """A remote MCP server contributing extra tools.

    Remote only, on purpose: a ``stdio`` server would let the librarian spawn a
    local process, and this brain gives its agent no shell. HTTP and SSE reach a
    service somebody else runs; nothing here can execute a command.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    transport: Literal["http", "sse"] = "http"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    insecure: bool = False
    """Skip TLS certificate verification (self-signed certs).

    Off by default: disabling it lets anyone on the network read and modify
    the traffic, so only enable this for a server you trust on a network you
    trust. Applies to both transports (``verify=False`` under the hood).
    """

    @model_validator(mode="before")
    @classmethod
    def _refuse_local_processes(cls, data: object) -> object:
        """Reject stdio servers with a reason, not just a schema error.

        Runs before validation so a config written against an older version —
        ``transport: stdio`` plus ``command`` — is told *why* it is refused.
        """
        if not isinstance(data, dict):
            return data
        raw: dict[str, object] = cast("dict[str, object]", data)
        if raw.get("transport") == "stdio" or "command" in raw:
            raise ValueError(
                "stdio MCP servers are not supported: the librarian has no shell "
                "and must not run local processes. Use a remote http or sse server."
            )
        return cast("object", data)

    @model_validator(mode="after")
    def _check_transport(self) -> MCPServerConfig:
        if not self.url:
            raise ValueError(f"mcp server {self.name!r}: {self.transport} needs a url")
        # Caught here rather than when an agent run tries to connect: a typo in the
        # config should fail the settings form, not a scheduled job.
        if not self.url.startswith(("http://", "https://")):
            raise ValueError(
                f"mcp server {self.name!r}: url must start with http:// or "
                f"https://, got {self.url!r}"
            )
        return self


class JobSpec(BaseModel):
    """One scheduled librarian run. Exactly one of ``every`` / ``cron``."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = ""
    description: str = ""
    enabled: bool = True
    every: str | None = None
    """Interval duration, e.g. ``"4h"``, ``"2d"``."""

    cron: str | None = None
    """Cron expression (croniter), e.g. ``"0 */4 * * *"``."""

    instructions: str = ""
    """Inline markdown prompt for the run."""

    instructions_file: str | None = None
    """Vault note whose markdown is the prompt (read at run time)."""

    tools: list[str] | None = None
    """Restrict to these tool names; ``None`` = every enabled tool."""

    mcp_servers: list[str] | None = None
    """Restrict to these MCP servers; ``None`` = every enabled server."""

    max_steps: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def _check_schedule(self) -> JobSpec:
        if (self.every is None) == (self.cron is None):
            raise ValueError(
                f"job {self.id!r}: set exactly one of 'every' (e.g. '4h') or 'cron'"
            )
        if self.every is not None:
            parse_duration(self.every)  # fail fast on typos
        if self.cron is not None and not croniter.is_valid(self.cron):
            raise ValueError(f"job {self.id!r}: invalid cron {self.cron!r}")
        return self


class AskConfig(BaseModel):
    """The interactive librarian: answering questions asked in the UI.

    Shaped like a job (own instructions note, tool/server restrictions, step
    budget) but with no schedule — one run per question, on demand. ``enabled``
    gates the whole function: the Ask page and ``POST /api/request`` refuse
    when it is off."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    """Off = the Ask page and ``POST /api/request`` refuse to run."""

    instructions_file: str | None = None
    """Vault note whose markdown scopes every answer (read at run time)."""

    tools: list[str] | None = None
    """Restrict to these tool names; ``None`` = every enabled tool."""

    mcp_servers: list[str] | None = None
    """Restrict to these MCP servers; ``None`` = every enabled server."""

    max_steps: int | None = Field(default=None, ge=1, le=200)


class SchedulerConfig(BaseModel):
    """How often the scheduler wakes to look for due jobs."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    """Off by default: the librarian should not act unprompted on a fresh install."""

    tick_seconds: int = Field(default=30, ge=1, le=3600)
    run_on_start: bool = False
    """Never-run jobs are due immediately instead of after one interval."""


#: The shipped schedule: a capture pipeline plus vault upkeep, all disabled.
#: Mirrored by ``brain.example.yaml`` (a test keeps the two in step) so the
#: settings view has something concrete to show on a fresh install instead of
#: an empty list. The pipeline flows one way: audit files requests → triage
#: rules on them → apply incorporates the approved ones; layout tends the
#: structure itself. Each job only gets the tools its stage needs.
_EXAMPLE_JOBS: tuple[dict[str, object], ...] = (
    {
        "id": "capture-triage",
        "name": "Capture triage",
        "description": (
            "Rule on pending capture entries: approve what is worth acting "
            "on, reject the rest."
        ),
        "enabled": False,
        "every": "4h",
        "instructions": (
            "List the pending capture queue. For each entry, read the notes it "
            "concerns and judge against the vault's current content and layout "
            "whether it is worth acting on. Worth it → approved (capture-apply "
            "incorporates it later); not worth it → rejected with the reason in "
            "the review note. Use approved or rejected only — never applied, "
            "applying belongs to capture-apply. Never edit the vault yourself, "
            "and never leave an entry pending silently.\n"
        ),
        "tools": ["list_capture", "read_note", "search_notes", "review_capture"],
    },
    {
        "id": "capture-apply",
        "name": "Capture apply",
        "description": (
            "Incorporate approved capture entries into the vault, then mark "
            "them applied."
        ),
        "enabled": False,
        "every": "1d",
        "instructions": (
            "List the approved capture queue and group the entries by note. "
            "For each group, decide from the entry content and the vault's "
            "current content and layout how to incorporate it, apply the "
            "change with the note tools, then move the entry to applied with "
            "review_capture — applied requires the written content, so pass "
            "what you wrote. If an entry went stale or is wrong, reject it "
            "with the reason instead. Never touch pending entries: triage "
            "owns those.\n"
        ),
        "tools": [
            "list_capture",
            "read_note",
            "search_notes",
            "create_note",
            "update_note",
            "append_note",
            "patch_note",
            "move_note",
            "review_capture",
        ],
    },
    {
        "id": "vault-layout",
        "name": "Vault layout",
        "description": (
            "Own the vault layout template: reshape notes and folders to match "
            "it as content evolves."
        ),
        "enabled": False,
        "cron": "0 3 * * 0",
        "instructions": (
            "Survey every note id and compare the layout against the vault "
            "layout template (admin/templates/layout, when it exists) and the "
            "vault's current content. Update the template itself when the "
            "content has outgrown it; create, update, patch or move individual "
            "notes and folders so the whole vault follows it. Never delete: "
            "file a capture request for removals or moves you are unsure of, "
            "and let triage rule on it.\n"
        ),
        "tools": [
            "list_notes",
            "read_note",
            "search_notes",
            "create_note",
            "update_note",
            "append_note",
            "patch_note",
            "move_note",
            "give_feedback",
        ],
    },
    {
        "id": "vault-audit",
        "name": "Vault audit",
        "description": (
            "Walk every note in turn and file a capture request for anything "
            "stale, wrong or missing."
        ),
        "enabled": False,
        "cron": "0 4 * * 6",
        "instructions": (
            "Walk every note in turn. For each one, consider whether it should "
            "be updated, removed or changed — then file a capture request "
            "(edit, missing or request) naming the note, what is wrong and "
            "where to get the right information. Never edit the vault "
            "yourself: you propose, triage rules, apply incorporates.\n"
        ),
        "tools": ["list_notes", "read_note", "search_notes", "give_feedback"],
    },
)


def default_jobs() -> list[JobSpec]:
    """Fresh copies of the shipped example schedule (never the shared objects)."""
    return [JobSpec.model_validate(job) for job in _EXAMPLE_JOBS]


class _YamlSource(PydanticBaseSettingsSource):
    """Settings source reading the YAML config file (missing file = empty)."""

    def __init__(self, settings_cls: type[BaseSettings], path: Path) -> None:
        super().__init__(settings_cls)
        self.path = path

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:  # pragma: no cover - unused
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"{self.path}: top level must be a mapping")
        return cast("dict[str, Any]", data)


class BrainConfigDocument(BaseModel):
    """The config schema, and nothing else.

    Validating a *document* (a PUT body, a saved row) must not consult the
    environment, the seed file or the database — a plain model cannot, which is
    exactly why the schema lives here and the layering lives in
    :class:`BrainConfig`. When these were one class, "the config file beat the
    values I just sent" was a real bug.
    """

    model_config = ConfigDict(extra="forbid")

    agent: AgentConfig = Field(default_factory=AgentConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    ask: AskConfig = Field(default_factory=AskConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    tools: dict[str, ToolConfig] = Field(default_factory=dict)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    jobs: list[JobSpec] = Field(default_factory=default_jobs)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_jobs(self) -> BrainConfigDocument:
        seen: set[str] = set()
        for job in self.jobs:
            if job.id in seen:
                raise ValueError(f"duplicate job id {job.id!r}")
            seen.add(job.id)
        servers = {s.name for s in self.mcp_servers}
        if len(servers) != len(self.mcp_servers):
            # Jobs and the UI reference servers by name, so duplicates are ambiguous.
            raise ValueError("duplicate mcp server name")
        for job in self.jobs:
            unknown = set(job.mcp_servers or ()) - servers
            if unknown:
                raise ValueError(
                    f"job {job.id!r}: unknown mcp server(s) {sorted(unknown)}"
                )
        ask_unknown = set(self.ask.mcp_servers or ()) - servers
        if ask_unknown:
            raise ValueError(f"ask: unknown mcp server(s) {sorted(ask_unknown)}")
        return self

    def redacted(self) -> dict[str, object]:
        """Config as a JSON-safe dict with the API token masked."""
        data: dict[str, Any] = self.model_dump(mode="json")
        agent = data.get("agent")
        if isinstance(agent, dict):
            agent_dict = cast("dict[str, object]", agent)
            if agent_dict.get("api_key"):
                agent_dict["api_key"] = MASK
        return data


class _DatabaseSource(PydanticBaseSettingsSource):
    """Settings saved by the settings page — the store of record."""

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:  # pragma: no cover - unused
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return SettingsStore(vault_root()).document()


class BrainConfig(BrainConfigDocument, BaseSettings):
    """The same schema, layered: env > database > seed file > defaults."""

    model_config = SettingsConfigDict(
        env_prefix="BRAIN__",
        env_nested_delimiter="__",
        extra="forbid",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Explicit > environment > saved settings > seed file > defaults.
        # ``init`` stays first so a direct construction (mostly tests) means what
        # it says; a saved document is a *source*, never an ``init`` value.
        return (
            init_settings,
            env_settings,
            _DatabaseSource(settings_cls),
            _YamlSource(settings_cls, config_path()),
            file_secret_settings,
        )


def config_path() -> Path:
    """Active config file: ``$BRAIN_CONFIG`` or ``./brain.yaml``."""
    return Path(os.environ.get("BRAIN_CONFIG", str(DEFAULT_CONFIG_FILE)))


def load_config(path: Path | None = None) -> BrainConfig:
    """Load and validate config; environment overrides the YAML file.

    Uses ``$BRAIN_CONFIG`` when ``path`` is omitted. Raises
    ``pydantic.ValidationError`` on malformed config.
    """
    if path is not None:
        os.environ["BRAIN_CONFIG"] = str(path)
    return BrainConfig()


def parse_config(data: dict[str, Any]) -> BrainConfigDocument:
    """Validate a config document exactly as given — no env, file or database.

    Used for writes: a PUT body must be applied verbatim, not merged with (or
    silently overridden by) the layers it replaces.
    """
    return BrainConfigDocument.model_validate(data)


def parse_config_yaml(text: str) -> dict[str, Any]:
    """YAML text → a plain dict, exactly like the file loader (no layering).

    Shared by the settings import endpoint and :func:`export_config_yaml`'s
    round trip: same parser, same "empty file/empty mapping is fine, anything
    else must be a mapping" rule the seed file follows.
    """
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("top level must be a mapping")
    return cast("dict[str, Any]", data)


def config_source() -> str:
    """Which layer the settings come from: database, file or defaults."""
    return SettingsStore(vault_root()).source(config_path())


def export_config_yaml(
    config: BrainConfigDocument | None = None, *, redact: bool = False
) -> str:
    """The *effective* config (defaults < file < database < env), as YAML.

    Loading this text back as the seed file reproduces the same config —
    field for field, byte for byte where it matters — because it is a plain
    dump of the merged document, not a diff against any one layer. The one
    thing that does not round-trip is an environment override: those still
    win over whatever the file says, same as today, so a pinned
    ``BRAIN__AGENT__MODEL`` continues to override this file exactly as it
    overrides the database now.

    Defaults to the current effective config (:func:`load_config`) — the same
    view ``GET /api/settings`` shows — so a caller does not have to assemble
    one first. ``redact=True`` masks the API key (see
    :meth:`BrainConfigDocument.redacted`), which is what a download-and-share
    path should use; the default is unredacted because a seed file that is
    missing its own key is not a faithful copy of the running config.
    """
    if config is None:
        config = load_config()
    data = config.redacted() if redact else config.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def save_config(config: BrainConfigDocument, path: Path | None = None) -> None:
    """Rejected: settings are stored in the vault database, not in a file.

    Kept as a tripwire so an old call site fails loudly instead of silently
    writing a second source of truth next to the database.
    """
    raise RuntimeError(
        "save_config() was removed: settings live in the vault database "
        "(see mysharedbrain.settings_store.SettingsStore). The YAML file is only "
        "ever read, as a seed."
    )
