"""TDD: the brain config — YAML file, env override, validation, masking."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from mysharedbrain.config import (
    MASK,
    AdminConfig,
    AgentConfig,
    BrainConfig,
    BrainConfigDocument,
    JobSpec,
    export_config_yaml,
    load_config,
    parse_config,
    parse_config_yaml,
    parse_duration,
)


@pytest.fixture()
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "brain.yaml"
    monkeypatch.setenv("BRAIN_CONFIG", str(path))
    return path


def test_temperature_defaults_to_a_careful_value(config_file: Path) -> None:
    """The librarian edits a shared vault: not a creative-writing default."""
    assert BrainConfig().agent.temperature == 0.2


def test_temperature_can_be_set_or_deferred(config_file: Path) -> None:
    assert BrainConfig(agent=AgentConfig(temperature=0.9)).agent.temperature == 0.9
    assert BrainConfig(agent=AgentConfig(temperature=None)).agent.temperature is None


def test_temperature_is_bounded() -> None:
    for bad in (-0.1, 2.1):
        with pytest.raises(ValidationError):
            AgentConfig(temperature=bad)


def test_defaults_when_file_absent(config_file: Path) -> None:
    cfg = load_config()
    assert cfg.agent.model
    assert cfg.scheduler.enabled is False, "the librarian must not act unprompted"
    assert [job.id for job in cfg.jobs] == [
        "capture-triage",
        "capture-apply",
        "vault-layout",
        "vault-audit",
    ]
    assert all(not job.enabled for job in cfg.jobs), "shipped schedule is off"


def test_example_file_matches_the_shipped_defaults(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`brain.example.yaml` is documentation for the real defaults, not a copy
    that can drift away from them."""
    example = Path(__file__).resolve().parents[2] / "brain.example.yaml"
    if not example.is_file():  # pragma: no cover - example lives at the repo root
        pytest.skip("brain.example.yaml not present")
    monkeypatch.setenv("BRAIN_CONFIG", str(example))
    documented = load_config()
    shipped = BrainConfig()
    assert [j.model_dump() for j in documented.jobs] == [
        j.model_dump() for j in shipped.jobs
    ]
    assert documented.scheduler.enabled is shipped.scheduler.enabled is False


def test_example_jobs_are_fresh_objects(config_file: Path) -> None:
    """Mutating one config's jobs must not leak into the next (no shared list)."""
    first = BrainConfig()
    first.jobs[0].enabled = True
    first.jobs.pop()
    second = BrainConfig()
    assert len(second.jobs) == 4
    assert second.jobs[0].enabled is False


def test_admin_defaults_point_at_the_vault_admin_section(
    config_file: Path,
) -> None:
    """Templates, prompts and the layout live in the vault under `admin/`."""
    cfg = BrainConfig()
    assert cfg.admin.dir == "admin"
    assert cfg.admin.layout_template == "admin/templates/layout"
    assert cfg.admin.templates == {}
    assert cfg.admin.prompts == {}


def test_admin_dir_rejects_unsafe_paths() -> None:
    for bad in ("/abs", "../escape", "a/../b", ".hidden/x", "", "   "):
        with pytest.raises(ValidationError):
            AdminConfig(dir=bad)


def test_admin_note_refs_must_be_safe_notes() -> None:
    with pytest.raises(ValidationError):
        AdminConfig(layout_template="/abs")
    with pytest.raises(ValidationError):
        AdminConfig(templates={"meeting": "../x"})
    with pytest.raises(ValidationError):
        AdminConfig(prompts={"triage": ".hidden/x"})


def test_admin_mapping_keys_are_slugs() -> None:
    with pytest.raises(ValidationError):
        AdminConfig(templates={"Bad Name!": "admin/templates/x"})
    with pytest.raises(ValidationError):
        AdminConfig(prompts={"": "admin/prompts/x"})
    cfg = AdminConfig(templates={"meeting": "admin/templates/meeting"})
    assert cfg.templates == {"meeting": "admin/templates/meeting"}


def test_example_file_documents_the_admin_defaults(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    example = Path(__file__).resolve().parents[2] / "brain.example.yaml"
    if not example.is_file():  # pragma: no cover - example lives at repo root
        pytest.skip("brain.example.yaml not present")
    monkeypatch.setenv("BRAIN_CONFIG", str(example))
    assert load_config().admin == BrainConfig().admin


def test_example_file_documents_the_ask_defaults(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    example = Path(__file__).resolve().parents[2] / "brain.example.yaml"
    if not example.is_file():  # pragma: no cover - example lives at repo root
        pytest.skip("brain.example.yaml not present")
    monkeypatch.setenv("BRAIN_CONFIG", str(example))
    assert load_config().ask == BrainConfig().ask


def test_yaml_file_loads_the_ask_section(config_file: Path) -> None:
    """The ask loop is configured from YAML, not UI-only."""
    config_file.write_text(
        yaml.safe_dump(
            {
                "ask": {
                    "enabled": False,
                    "instructions_file": "ask-policy",
                    "tools": ["read_note", "search_notes"],
                    "max_steps": 10,
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.ask.enabled is False
    assert cfg.ask.instructions_file == "ask-policy"
    assert cfg.ask.tools == ["read_note", "search_notes"]
    assert cfg.ask.max_steps == 10


def test_yaml_file_loads_admin_and_mcp_insecure(config_file: Path) -> None:
    """Every newer setting must be YAML-configurable, not UI-only."""
    config_file.write_text(
        yaml.safe_dump(
            {
                "admin": {
                    "dir": "meta",
                    "layout_template": "meta/layout",
                    "templates": {"meeting": "meta/tpl/meeting"},
                    "prompts": {"triage": "meta/prompts/triage"},
                },
                "mcp_servers": [
                    {
                        "name": "lab",
                        "transport": "http",
                        "url": "https://lab/mcp",
                        "headers": {"Authorization": "Bearer x"},
                        "insecure": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.admin.dir == "meta"
    assert cfg.admin.layout_template == "meta/layout"
    assert cfg.admin.templates == {"meeting": "meta/tpl/meeting"}
    assert cfg.admin.prompts == {"triage": "meta/prompts/triage"}
    (server,) = cfg.mcp_servers
    assert server.insecure is True
    assert server.headers == {"Authorization": "Bearer x"}


def test_env_overrides_admin_dir(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN__ADMIN__DIR", "meta")
    assert load_config().admin.dir == "meta"


def test_exported_yaml_round_trips_into_an_identical_config(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Feed the export back in as the seed file: same effective config."""
    config_file.write_text(
        yaml.safe_dump(
            {
                "agent": {"model": "openai:gpt-4o", "api_key": "sk-secret"},
                "admin": {"dir": "meta"},
                "mcp_servers": [
                    {
                        "name": "lab",
                        "transport": "http",
                        "url": "https://lab/mcp",
                        "insecure": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    original = load_config()
    exported = export_config_yaml(original)

    reseeded = config_file.parent / "exported.yaml"
    reseeded.write_text(exported, encoding="utf-8")
    monkeypatch.setenv("BRAIN_CONFIG", str(reseeded))

    round_tripped = load_config()
    assert round_tripped.model_dump(mode="json") == original.model_dump(mode="json")


def test_export_defaults_to_the_effective_config(config_file: Path) -> None:
    """No args: exports what GET /api/settings would show right now."""
    config_file.write_text(
        yaml.safe_dump({"agent": {"model": "openai:gpt-4o"}}), encoding="utf-8"
    )
    exported = export_config_yaml()
    assert yaml.safe_load(exported)["agent"]["model"] == "openai:gpt-4o"


def test_export_can_redact_the_api_key(config_file: Path) -> None:
    cfg = BrainConfigDocument(agent=AgentConfig(api_key="sk-secret"))
    assert "sk-secret" not in export_config_yaml(cfg, redact=True)
    assert MASK in export_config_yaml(cfg, redact=True)
    assert "sk-secret" in export_config_yaml(cfg, redact=False)


def test_env_override_still_wins_over_an_exported_seed_file(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export is a faithful seed file, not a way to escape env precedence."""
    config_file.write_text(
        yaml.safe_dump({"agent": {"model": "openai:gpt-4o"}}), encoding="utf-8"
    )
    exported = export_config_yaml()
    reseeded = config_file.parent / "exported.yaml"
    reseeded.write_text(exported, encoding="utf-8")
    monkeypatch.setenv("BRAIN_CONFIG", str(reseeded))
    monkeypatch.setenv("BRAIN__AGENT__MODEL", "from-env")

    assert load_config().agent.model == "from-env"


def test_parse_config_yaml_matches_the_file_loader() -> None:
    text = yaml.safe_dump({"agent": {"model": "openai:gpt-4o"}})
    assert parse_config_yaml(text) == {"agent": {"model": "openai:gpt-4o"}}


def test_parse_config_yaml_empty_document_is_an_empty_mapping() -> None:
    assert parse_config_yaml("") == {}
    assert parse_config_yaml("# just a comment") == {}


def test_parse_config_yaml_rejects_a_non_mapping_top_level() -> None:
    with pytest.raises(ValueError, match="top level must be a mapping"):
        parse_config_yaml("- a\n- list")


def test_duration_parsing() -> None:
    assert parse_duration("30s") == 30
    assert parse_duration("15m") == 900
    assert parse_duration("4h") == 14400
    assert parse_duration("2d") == 172800
    assert parse_duration(" 4H ") == 14400
    with pytest.raises(ValueError):
        parse_duration("4 hours")


def test_yaml_file_is_loaded(config_file: Path) -> None:
    config_file.write_text(
        yaml.safe_dump(
            {
                "agent": {"model": "openai:gpt-4o", "instructions_file": "brain.md"},
                "jobs": [
                    {
                        "id": "sweep",
                        "every": "2d",
                        "description": "consolidate notes",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.agent.model == "openai:gpt-4o"
    assert cfg.jobs[0].id == "sweep"
    assert cfg.jobs[0].every == "2d"


def test_env_overrides_file(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file.write_text(
        yaml.safe_dump({"agent": {"model": "openai:gpt-4o-mini"}}), encoding="utf-8"
    )
    monkeypatch.setenv("BRAIN__AGENT__MODEL", "anthropic:claude-sonnet-4")
    assert load_config().agent.model == "anthropic:claude-sonnet-4"


def test_parse_config_beats_file_and_env(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writes must apply the given document verbatim, not merge sources."""
    from mysharedbrain.config import parse_config

    config_file.write_text(
        yaml.safe_dump(
            {"agent": {"model": "from-file"}, "jobs": [{"id": "old", "every": "1h"}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BRAIN__AGENT__MODEL", "from-env")
    cfg = parse_config({"agent": {"model": "from-body"}, "jobs": []})
    assert cfg.agent.model == "from-body"
    assert cfg.jobs == []


def test_redacted_masks_token(config_file: Path) -> None:
    config_file.write_text(
        yaml.safe_dump({"agent": {"api_key": "sk-secret"}}), encoding="utf-8"
    )
    cfg = load_config()
    data = cfg.redacted()
    assert data["agent"]["api_key"] == MASK  # type: ignore[index]


def test_job_requires_exactly_one_schedule() -> None:
    with pytest.raises(ValidationError):
        JobSpec(id="a")
    with pytest.raises(ValidationError):
        JobSpec(id="a", every="1h", cron="0 * * * *")


def test_job_rejects_bad_duration_and_cron() -> None:
    with pytest.raises(ValidationError):
        JobSpec(id="a", every="soon")
    with pytest.raises(ValidationError):
        JobSpec(id="a", cron="not a cron")


def test_job_cron_is_validated_as_usable() -> None:
    assert JobSpec(id="a", cron="*/30 * * * *").cron == "*/30 * * * *"


def test_duplicate_job_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        BrainConfig(jobs=[JobSpec(id="a", every="1h"), JobSpec(id="a", every="2h")])


def test_job_mcp_server_must_exist() -> None:
    with pytest.raises(ValidationError):
        BrainConfig(
            jobs=[JobSpec(id="a", every="1h", mcp_servers=["ghost"])],
        )


def test_mcp_server_transport_requirements() -> None:
    from mysharedbrain.config import MCPServerConfig

    with pytest.raises(ValidationError):
        MCPServerConfig(name="x", transport="http")
    assert MCPServerConfig(name="x", url="http://h/mcp").url == "http://h/mcp"
    assert (
        MCPServerConfig(name="x", transport="sse", url="https://h/sse").transport
        == "sse"
    )


def test_mcp_servers_cannot_be_stdio() -> None:
    """The librarian has no shell: a local MCP command would be one. Refused,
    with a reason, and the old config shape is called out explicitly."""
    from mysharedbrain.config import MCPServerConfig

    with pytest.raises(ValidationError, match="librarian has no shell"):
        MCPServerConfig.model_validate(
            {"name": "x", "transport": "stdio", "url": "http://h/mcp"}
        )
    with pytest.raises(ValidationError, match="librarian has no shell"):
        # pre-removal config: transport omitted, command given
        MCPServerConfig.model_validate(
            {"name": "x", "command": "uvx", "args": ["some-server"]}
        )
    with pytest.raises(ValidationError):
        # the field is gone, so it cannot be smuggled in under another key either
        MCPServerConfig.model_validate(
            {"name": "x", "url": "http://h/mcp", "args": ["--shell"]}
        )


def test_mcp_server_verifies_tls_by_default() -> None:
    from mysharedbrain.config import MCPServerConfig

    assert MCPServerConfig(name="x", url="https://h/mcp").insecure is False


def test_insecure_mcp_server_disables_certificate_verification() -> None:
    """Self-signed certs: `insecure` maps onto the transport's `verify`."""
    from mysharedbrain.agent import mcp_transport
    from mysharedbrain.config import MCPServerConfig

    assert mcp_transport(MCPServerConfig(name="a", url="https://h/mcp")).verify is None
    assert (
        mcp_transport(
            MCPServerConfig(name="b", url="https://h/mcp", insecure=True)
        ).verify
        is False
    )
    assert (
        mcp_transport(
            MCPServerConfig(
                name="c", transport="sse", url="https://h/sse", insecure=True
            )
        ).verify
        is False
    )


def test_only_remote_transports_reach_the_transport_builder() -> None:
    """Belt and braces: whatever the config says, the builder is remote-only."""
    from fastmcp.client.transports import SSETransport, StreamableHttpTransport

    from mysharedbrain.agent import mcp_transport
    from mysharedbrain.config import MCPServerConfig

    assert isinstance(
        mcp_transport(MCPServerConfig(name="a", url="http://h/mcp")),
        StreamableHttpTransport,
    )
    assert isinstance(
        mcp_transport(MCPServerConfig(name="b", transport="sse", url="https://h/sse")),
        SSETransport,
    )


def test_mcp_server_url_must_be_http() -> None:
    """A typo'd URL should fail the settings form, not a scheduled job run."""
    from mysharedbrain.config import MCPServerConfig

    for bad in ("asd", "example.com/mcp", "ftp://host/mcp"):
        with pytest.raises(ValidationError, match="http://"):
            MCPServerConfig(name="x", url=bad)
    assert MCPServerConfig(name="x", url="https://h/mcp").url == "https://h/mcp"


def test_broken_local_config_cannot_leak_into_tests() -> None:
    """Regression: a developer's ./brain.yaml silently changed test results.

    The autouse fixture pins BRAIN_CONFIG away from the working directory, so a
    default-config load never reads it.
    """
    from mysharedbrain.config import config_path

    assert config_path().name == "isolated-brain.yaml"
    assert not config_path().exists()


def test_saved_settings_land_in_the_database_not_a_file(
    config_file: Path, vault_dir: Path
) -> None:
    """Settings are state: they belong in `.brain/brain.db`, and the seed file is
    never written."""
    from mysharedbrain.settings_store import SettingsStore

    store = SettingsStore(vault_dir)
    store.save(
        parse_config({"jobs": [{"id": "sweep", "every": "2d"}]}).model_dump(mode="json")
    )

    reloaded = load_config()
    assert [j.id for j in reloaded.jobs] == ["sweep"]
    assert store.get() is not None
    assert not config_file.exists(), "the YAML file is read-only"
    assert store.source(config_file) == "database"


def test_stored_settings_survive_the_seed_file_disappearing(
    config_file: Path, vault_dir: Path
) -> None:
    from mysharedbrain.settings_store import SettingsStore

    config_file.write_text("agent:\n  model: from-seed\n", encoding="utf-8")
    SettingsStore(vault_dir).save(
        parse_config({"agent": {"model": "from-db"}}).model_dump(mode="json")
    )
    config_file.unlink()

    assert load_config().agent.model == "from-db"


def test_the_database_beats_the_seed_file(config_file: Path, vault_dir: Path) -> None:
    from mysharedbrain.settings_store import SettingsStore

    config_file.write_text("agent:\n  model: from-seed\n", encoding="utf-8")
    assert load_config().agent.model == "from-seed"

    SettingsStore(vault_dir).save(
        parse_config({"agent": {"model": "from-db"}}).model_dump(mode="json")
    )
    assert load_config().agent.model == "from-db"


def test_the_environment_beats_the_database(
    config_file: Path, vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A container's env (secrets, deployment-specific values) still wins."""
    from mysharedbrain.settings_store import SettingsStore

    SettingsStore(vault_dir).save(
        parse_config({"agent": {"model": "from-db"}}).model_dump(mode="json")
    )
    monkeypatch.setenv("BRAIN__AGENT__MODEL", "from-env")

    assert load_config().agent.model == "from-env"


def test_config_source_reports_the_active_layer(
    config_file: Path, vault_dir: Path
) -> None:
    from mysharedbrain.config import config_source
    from mysharedbrain.settings_store import SettingsStore

    assert config_source() == "defaults"
    config_file.write_text("agent:\n  model: from-seed\n", encoding="utf-8")
    assert config_source() == "file"
    SettingsStore(vault_dir).save(
        parse_config({"agent": {"model": "from-db"}}).model_dump(mode="json")
    )
    assert config_source() == "database"
    SettingsStore(vault_dir).clear()
    assert config_source() == "file"


def test_a_corrupt_settings_row_falls_back_to_the_seed(
    config_file: Path, vault_dir: Path
) -> None:
    """Half-written JSON must not brick the app, and must not be trusted."""
    from mysharedbrain.db import Database
    from mysharedbrain.settings_store import SettingsStore

    config_file.write_text("agent:\n  model: from-seed\n", encoding="utf-8")
    store = SettingsStore(vault_dir)
    store.save({"agent": {"model": "from-db"}})
    with Database(vault_dir).transaction() as conn:
        conn.execute("UPDATE settings SET document = ? WHERE id = 1", ("{not json",))

    assert store.get() is None
    assert load_config().agent.model == "from-seed"
    assert store.source(config_file) == "file"


def test_saving_no_jobs_does_not_resurrect_the_examples(
    config_file: Path, vault_dir: Path
) -> None:
    """Regression: an emptied list used to be indistinguishable from "unset",
    which reloaded as the shipped schedule again — deleting every job undid
    itself."""
    from mysharedbrain.settings_store import SettingsStore

    SettingsStore(vault_dir).save(parse_config({"jobs": []}).model_dump(mode="json"))
    assert load_config().jobs == []
