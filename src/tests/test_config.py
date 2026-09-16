"""TDD: the brain config — YAML file, env override, validation, masking."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from mysharedbrain.config import (
    MASK,
    AgentConfig,
    BrainConfig,
    JobSpec,
    load_config,
    parse_config,
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
        "vault-sweep",
        "source-check",
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
    assert len(second.jobs) == 3
    assert second.jobs[0].enabled is False


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
