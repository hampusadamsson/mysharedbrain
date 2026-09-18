"""TDD: settings API — read/update config, run jobs, run history."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from mysharedbrain.agent import AgentOutcome, ConnectionCheck
from mysharedbrain.app import create_app
from mysharedbrain.config import MASK, BrainConfigDocument

CONFIG_PATH = "/api/settings"


@pytest.fixture()
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "brain.yaml"
    monkeypatch.setenv("BRAIN_CONFIG", str(path))
    return path


def client() -> TestClient:
    return TestClient(create_app())


def _job(job_id: str = "sweep", **extra: object) -> dict[str, object]:
    return {"id": job_id, "every": "2d", "instructions": "tidy", **extra}


def test_get_settings_returns_config_tools_and_path(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    body = client().get(CONFIG_PATH).json()
    # a fresh install shows the shipped (disabled) schedule rather than nothing
    assert [j["id"] for j in body["jobs"]] == [
        "capture-triage",
        "capture-apply",
        "vault-layout",
        "vault-audit",
    ]
    assert all(j["enabled"] is False for j in body["jobs"])
    assert all(j["next_run"] == "" for j in body["jobs"]), "nothing may be scheduled"
    assert body["config"]["scheduler"]["enabled"] is False
    assert body["config_path"] == str(config_file)
    assert body["api_key_configured"] is False
    names = {t["name"] for t in body["tools"]}
    assert {"read_note", "review_capture", "patch_note"} <= names
    assert all(t["enabled"] for t in body["tools"])


def test_put_settings_stores_the_document_in_the_database(
    vault_dir: Path, config_file: Path
) -> None:
    """The seed file is never written: settings live in `.brain/brain.db`."""
    from mysharedbrain.settings_store import SettingsStore

    c = client()
    payload = {"config": {"jobs": [_job()], "agent": {"model": "openai:gpt-4o"}}}
    body = c.put(CONFIG_PATH, json=payload).json()
    assert body["jobs"][0]["id"] == "sweep"
    assert body["jobs"][0]["schedule"] == "2d"
    assert body["config_source"] == "database"

    stored = SettingsStore(vault_dir).get()
    assert stored is not None
    assert stored.document["agent"]["model"] == "openai:gpt-4o"
    assert [j["id"] for j in stored.document["jobs"]] == ["sweep"]
    assert not config_file.exists(), "nothing should be written to a file"
    # a fresh GET reflects the saved document
    assert c.get(CONFIG_PATH).json()["config"]["jobs"][0]["id"] == "sweep"


def test_put_settings_rejects_invalid_config(
    vault_dir: Path, config_file: Path
) -> None:
    c = client()
    bad = {"config": {"jobs": [{"id": "sweep"}]}}  # no every/cron
    res = c.put(CONFIG_PATH, json=bad)
    assert res.status_code == 400
    assert "invalid config" in res.json()["detail"]
    from mysharedbrain.settings_store import SettingsStore

    assert SettingsStore(vault_dir).get() is None, "nothing stored on failure"
    assert not config_file.exists(), "nothing written on failure"


def test_put_settings_beats_the_seed_file(vault_dir: Path, config_file: Path) -> None:
    """Regression: a settings model validates through its sources, so an
    explicit body must beat the seed file it is replacing."""
    config_file.write_text(
        yaml.safe_dump(
            {
                "agent": {"model": "openai:gpt-4o"},
                "jobs": [{"id": "old", "every": "1h"}],
                "tools": {"delete_note": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )
    c = client()
    body = c.get(CONFIG_PATH).json()
    assert [j["id"] for j in body["jobs"]] == ["old"]

    config = body["config"]
    config["jobs"] = [_job("new")]
    config["tools"]["delete_note"] = {"enabled": True}
    saved = c.put(CONFIG_PATH, json={"config": config}).json()
    assert [j["id"] for j in saved["jobs"]] == ["new"]
    assert {t["name"]: t["enabled"] for t in saved["tools"]}["delete_note"] is True
    assert saved["config_source"] == "database"
    # saved settings win over the seed file, and survive it going away
    assert [j["id"] for j in c.get(CONFIG_PATH).json()["jobs"]] == ["new"]
    config_file.unlink()
    assert [j["id"] for j in c.get(CONFIG_PATH).json()["jobs"]] == ["new"]


def test_put_settings_masking_keeps_stored_token(
    vault_dir: Path, config_file: Path
) -> None:
    from mysharedbrain.settings_store import SettingsStore

    c = client()
    c.put(CONFIG_PATH, json={"config": {"agent": {"api_key": "sk-secret"}}})
    body = c.get(CONFIG_PATH).json()
    assert body["config"]["agent"]["api_key"] == MASK

    # UI sends the mask back unchanged -> the real token survives
    sent = body["config"]
    c.put(CONFIG_PATH, json={"config": sent})
    stored = SettingsStore(vault_dir).get()
    assert stored is not None
    assert stored.document["agent"]["api_key"] == "sk-secret"
    assert not config_file.exists()


def test_tool_toggle_round_trip(vault_dir: Path, config_file: Path) -> None:
    c = client()
    c.put(CONFIG_PATH, json={"config": {"tools": {"delete_note": {"enabled": False}}}})
    tools = {t["name"]: t["enabled"] for t in c.get(CONFIG_PATH).json()["tools"]}
    assert tools["delete_note"] is False
    assert tools["read_note"] is True


def test_put_settings_round_trips_the_admin_section(
    vault_dir: Path, config_file: Path
) -> None:
    c = client()
    assert c.get(CONFIG_PATH).json()["config"]["admin"]["dir"] == "admin"
    config = c.get(CONFIG_PATH).json()["config"]
    config["admin"] = {
        "dir": "meta",
        "layout_template": "meta/layout",
        "templates": {"meeting": "meta/tpl/meeting"},
        "prompts": {"triage": "meta/prompts/triage"},
    }
    saved = c.put(CONFIG_PATH, json={"config": config}).json()
    assert saved["config"]["admin"]["dir"] == "meta"
    assert saved["config"]["admin"]["templates"] == {"meeting": "meta/tpl/meeting"}


def test_export_endpoint_returns_yaml_that_reseeds_to_the_same_config(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    c = client()
    config = c.get(CONFIG_PATH).json()["config"]
    config["agent"]["model"] = "openai:gpt-4o"
    c.put(CONFIG_PATH, json={"config": config})

    resp = c.get("/api/settings/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    exported = yaml.safe_load(resp.text)
    assert exported["agent"]["model"] == "openai:gpt-4o"
    # redacted for the download-and-share path
    assert "sk-secret" not in resp.text

    reseeded = config_file.parent / "exported.yaml"
    reseeded.write_text(resp.text, encoding="utf-8")
    monkeypatch.setenv("BRAIN_CONFIG", str(reseeded))
    from mysharedbrain.service import vault_root
    from mysharedbrain.settings_store import SettingsStore

    SettingsStore(vault_root()).clear()  # drop the DB layer, seed file only now
    reseeded_config = client().get(CONFIG_PATH).json()["config"]
    assert reseeded_config["agent"]["model"] == "openai:gpt-4o"


def test_import_settings_accepts_pasted_yaml(
    vault_dir: Path, config_file: Path
) -> None:
    c = client()
    resp = c.put(
        "/api/settings/import",
        json={
            "yaml": yaml.safe_dump(
                {"agent": {"model": "openai:gpt-4o"}, "admin": {"dir": "meta"}}
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["config"]["agent"]["model"] == "openai:gpt-4o"
    assert body["config"]["admin"]["dir"] == "meta"
    # actually saved, not just echoed back
    assert c.get(CONFIG_PATH).json()["config"]["admin"]["dir"] == "meta"


def test_import_settings_rejects_bad_yaml(vault_dir: Path, config_file: Path) -> None:
    c = client()
    resp = c.put("/api/settings/import", json={"yaml": "agent: [oops"})
    assert resp.status_code == 400
    assert "invalid yaml" in resp.json()["detail"]


def test_import_settings_rejects_a_non_mapping_document(
    vault_dir: Path, config_file: Path
) -> None:
    c = client()
    resp = c.put("/api/settings/import", json={"yaml": "- just\n- a\n- list"})
    assert resp.status_code == 400


def test_import_settings_rejects_invalid_config(
    vault_dir: Path, config_file: Path
) -> None:
    c = client()
    resp = c.put("/api/settings/import", json={"yaml": "agent: {model: 1}"})
    assert resp.status_code == 400


def test_export_then_import_round_trips_through_another_install(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: extract config, paste it elsewhere, same effective
    config (masked token aside — that always needs re-entry after a real
    export, by design)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    c = client()
    config = c.get(CONFIG_PATH).json()["config"]
    config["agent"]["model"] = "openai:gpt-4o"
    config["admin"]["dir"] = "meta"
    c.put(CONFIG_PATH, json={"config": config})
    exported = c.get("/api/settings/export").text

    imported = c.put("/api/settings/import", json={"yaml": exported}).json()
    assert imported["config"]["agent"]["model"] == "openai:gpt-4o"
    assert imported["config"]["admin"]["dir"] == "meta"


def test_put_settings_round_trips_mcp_insecure_flag(
    vault_dir: Path, config_file: Path
) -> None:
    c = client()
    config = c.get(CONFIG_PATH).json()["config"]
    config["mcp_servers"] = [
        {"name": "lab", "transport": "http", "url": "https://lab/mcp", "insecure": True}
    ]
    saved = c.put(CONFIG_PATH, json={"config": config}).json()
    assert saved["config"]["mcp_servers"][0]["insecure"] is True


def test_put_settings_rejects_unknown_tool(vault_dir: Path, config_file: Path) -> None:
    res = client().put(
        CONFIG_PATH, json={"config": {"tools": {"nuke": {"enabled": True}}}}
    )
    assert res.status_code == 400


def test_the_app_lifespan_starts_and_stops_the_scheduler(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scheduler is only useful if the app actually starts it."""
    from mysharedbrain.jobs import get_scheduler, reset_scheduler

    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="ran", requests=1, tool_calls=0)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    config_file.write_text(
        yaml.safe_dump(
            {
                "scheduler": {
                    "enabled": True,
                    "tick_seconds": 1,
                    "run_on_start": True,
                },
                "jobs": [{"id": "sweep", "every": "1h"}],
            }
        ),
        encoding="utf-8",
    )
    reset_scheduler()

    with TestClient(create_app()):
        assert get_scheduler().is_running is True, "lifespan should start the loop"

    assert get_scheduler().is_running is False, "lifespan should stop it again"
    # and it did the work while it was up
    assert get_scheduler().store.last("sweep") is not None


def test_run_job_endpoint_records_run(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="swept the vault", requests=1, tool_calls=3)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    c = client()
    c.put(CONFIG_PATH, json={"config": {"jobs": [_job()]}})
    run = c.post(f"{CONFIG_PATH}/jobs/sweep/run").json()
    assert run["status"] == "ok"
    assert "swept the vault" in run["detail"]

    runs = c.get(f"{CONFIG_PATH}/jobs/sweep/runs").json()["runs"]
    assert len(runs) == 1
    assert runs[0]["job_id"] == "sweep"


def test_test_mcp_server_endpoint_reports_failure(
    vault_dir: Path, config_file: Path
) -> None:
    """The check answers 200 with ok=false — an unreachable server is not a
    server error, it is the answer to the question."""
    body = (
        client()
        .post(
            f"{CONFIG_PATH}/mcp/test",
            json={"name": "dead", "transport": "http", "url": "http://127.0.0.1:9/mcp"},
        )
        .json()
    )
    assert body["ok"] is False
    assert body["name"] == "dead"
    assert body["tools"] == []
    assert body["detail"]


def test_test_mcp_server_endpoint_validates_the_config(
    vault_dir: Path, config_file: Path
) -> None:
    res = client().post(f"{CONFIG_PATH}/mcp/test", json={"name": "x", "url": "asd"})
    assert res.status_code == 422
    assert "http://" in str(res.json())


def test_test_model_endpoint_reports_a_failure(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same shape as the MCP check, and a missing token is the common red line."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    body = (
        client()
        .post(
            f"{CONFIG_PATH}/model/test",
            json={"model": "openai:gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"},
        )
        .json()
    )
    assert body["ok"] is False
    assert body["name"] == "openai:gpt-4o-mini"
    assert body["tools"] == []
    assert "OPENAI_API_KEY" in body["detail"]


def test_test_model_endpoint_resolves_the_masked_token(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The form sends the mask back; the check must use the stored token, not the
    literal asterisks — and must not talk to a provider to prove it."""
    seen: list[str] = []

    async def fake_check(cfg: BrainConfigDocument, **_: object) -> ConnectionCheck:
        agent = cfg.agent
        seen.append(agent.api_key)
        return ConnectionCheck(name=agent.model, ok=True, detail="answered", tools=[])

    monkeypatch.setattr("mysharedbrain.api_settings.check_model", fake_check)
    c = client()
    c.put(CONFIG_PATH, json={"config": {"agent": {"api_key": "sk-stored"}}})

    body = c.post(
        f"{CONFIG_PATH}/model/test",
        json={"model": "openai:gpt-4o-mini", "api_key": MASK},
    ).json()
    assert body["ok"] is True
    assert seen == ["sk-stored"], "the mask must not reach the provider"


def test_test_model_endpoint_validates_the_body(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check(cfg: BrainConfigDocument, **_: object) -> ConnectionCheck:
        return ConnectionCheck(name="x", ok=True, detail="answered", tools=[])

    monkeypatch.setattr("mysharedbrain.api_settings.check_model", fake_check)
    c = client()
    # defaults are accepted (the shipped model), junk is not
    assert c.post(f"{CONFIG_PATH}/model/test", json={}).status_code == 200
    assert (
        c.post(f"{CONFIG_PATH}/model/test", json={"temperature": 9}).status_code == 422
    )
    assert c.post(f"{CONFIG_PATH}/model/test", json={"max_steps": 0}).status_code == 422


def test_mcp_server_names_must_be_unique(vault_dir: Path, config_file: Path) -> None:
    """Jobs and the settings rows reference servers by name."""
    res = client().put(
        CONFIG_PATH,
        json={
            "config": {
                "mcp_servers": [
                    {"name": "dup", "url": "https://a/mcp"},
                    {"name": "dup", "url": "https://b/mcp"},
                ]
            }
        },
    )
    assert res.status_code == 400
    assert "duplicate" in res.json()["detail"]


def test_run_job_unknown_returns_404(vault_dir: Path, config_file: Path) -> None:
    assert client().post(f"{CONFIG_PATH}/jobs/ghost/run").status_code == 404


def test_manual_run_is_logged_and_tagged_librarian(
    vault_dir: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(
        cfg: object, lib: object, prompt: str, job: object = None
    ) -> AgentOutcome:
        return AgentOutcome(output="triaged", requests=1, tool_calls=0)

    monkeypatch.setattr("mysharedbrain.jobs.run_agent", fake)
    c = client()
    c.put(CONFIG_PATH, json={"config": {"jobs": [_job()]}})
    c.post(f"{CONFIG_PATH}/jobs/sweep/run")

    entries = c.get("/api/audit").json()["entries"]
    assert [(e["actor"], e["action"]) for e in entries] == [("librarian", "job-ok")]
    assert "job:sweep" in entries[0]["detail"]


def test_run_on_start_flag_exposed(vault_dir: Path, config_file: Path) -> None:
    c = client()
    c.put(CONFIG_PATH, json={"config": {"scheduler": {"run_on_start": True}}})
    body = c.get(CONFIG_PATH).json()
    assert body["config"]["scheduler"]["run_on_start"] is True
