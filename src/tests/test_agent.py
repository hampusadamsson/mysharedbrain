"""TDD: agent wiring — instructions, tool selection, real run via test model."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings

from mysharedbrain.agent import (
    build_agent,
    build_model,
    check_model,
    load_instructions,
    model_string,
    provider_kwargs,
    run_agent,
)
from mysharedbrain.config import (
    AdminConfig,
    AgentConfig,
    BrainConfig,
    BrainConfigDocument,
    MCPServerConfig,
    ProviderConfig,
    ToolConfig,
)
from mysharedbrain.service import Librarian

TEST_MODEL = TestModel(call_tools=[], custom_output_text="noted")


def _lib(root: Path) -> Librarian:
    return Librarian(root, actor="test")


def _stub_provider(*params: str) -> type[Any]:
    """A provider class whose constructor takes exactly ``params``.

    Lets the signature-driven translation in :func:`_provider_kwargs` be tested
    against providers whose SDKs are not installed here (azure, litellm).
    """
    import inspect as _inspect

    class Stub:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = dict(kwargs)

    Stub.__init__.__signature__ = _inspect.Signature(  # type: ignore[attr-defined]
        [_inspect.Parameter("self", _inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        + [
            _inspect.Parameter(p, _inspect.Parameter.POSITIONAL_OR_KEYWORD, default="")
            for p in params
        ]
    )
    return Stub


def _cfg(**agent: object) -> BrainConfigDocument:
    return BrainConfigDocument(agent=AgentConfig(**agent))  # type: ignore[arg-type]


def test_load_instructions_names_the_admin_section(vault_dir: Path) -> None:
    """The librarian is told where templates, prompts and the layout live."""
    text = load_instructions(BrainConfigDocument(), _lib(vault_dir))
    assert "admin/" in text
    assert "admin/templates/layout" in text
    assert "admin/templates/" in text
    assert "admin/prompts/" in text


def test_load_instructions_uses_the_configured_admin_paths(vault_dir: Path) -> None:
    cfg = BrainConfigDocument(
        admin=AdminConfig(
            dir="meta",
            layout_template="meta/layout",
            templates={"meeting": "meta/tpl/meeting"},
            prompts={"triage": "meta/prompts/triage"},
        )
    )
    text = load_instructions(cfg, _lib(vault_dir))
    assert "meta/" in text
    assert "meta/layout" in text
    assert "meeting" in text and "meta/tpl/meeting" in text
    assert "triage" in text and "meta/prompts/triage" in text


def test_provider_kwargs_map_base_url_to_the_provider_parameter() -> None:
    """The SDKs disagree on the name (`base_url` vs `azure_endpoint` vs
    `api_base`), so the mapping is read from the constructor's signature."""
    cases = {
        "openai": (("base_url", "api_key"), "base_url"),
        "azure": (("azure_endpoint", "api_version", "api_key"), "azure_endpoint"),
        "litellm": (("api_base", "api_key"), "api_base"),
    }
    for _provider, (params, expected) in cases.items():
        cfg = _cfg(provider=ProviderConfig(name="x", base_url="http://box/v1"))
        kwargs = provider_kwargs(_stub_provider(*params), cfg)
        assert kwargs[expected] == "http://box/v1"


def test_provider_kwargs_carry_the_api_version_and_token() -> None:
    cfg = _cfg(api_key="sk-x", provider=ProviderConfig(api_version="2024-10-21"))
    kwargs = provider_kwargs(
        _stub_provider("azure_endpoint", "api_version", "api_key"), cfg
    )
    assert kwargs == {"api_version": "2024-10-21", "api_key": "sk-x"}


def test_provider_kwargs_pass_extra_options_by_name() -> None:
    """Anything else the provider needs goes through `options`, by its own
    argument name — the escape hatch for the long tail of providers."""
    cfg = _cfg(api_key="sk-x", provider=ProviderConfig(options={"region": "eu-west-1"}))
    kwargs = provider_kwargs(_stub_provider("region", "api_key"), cfg)
    assert kwargs == {"region": "eu-west-1", "api_key": "sk-x"}


def test_provider_kwargs_reject_an_option_the_provider_does_not_take() -> None:
    """Silently dropping an unknown option would look like it worked."""
    cfg = _cfg(provider=ProviderConfig(options={"nonsense": "1"}))
    with pytest.raises(ValueError, match="does not accept nonsense"):
        provider_kwargs(_stub_provider("base_url"), cfg)


def test_provider_kwargs_refuse_a_url_the_provider_cannot_take() -> None:
    cfg = _cfg(provider=ProviderConfig(base_url="http://h/v1"))
    with pytest.raises(ValueError, match="does not accept base_url"):
        provider_kwargs(_stub_provider("api_key"), cfg)


def test_build_model_reaches_the_configured_endpoint() -> None:
    """Real provider class, real base_url — nothing here connects anywhere.

    `ollama` is openai-compatible, so its provider is importable without extra
    SDKs and the endpoint is observable on the built model.
    """
    cfg = _cfg(
        model="llama3.1",
        provider=ProviderConfig(name="ollama", base_url="http://localhost:11434/v1"),
    )
    model = build_model(cfg)
    assert model.model_name == "llama3.1"
    assert str(model.provider.base_url).startswith("http://localhost:11434/v1")  # type: ignore[attr-defined]


def test_build_model_opencode_defaults_to_zen_endpoint() -> None:
    """`opencode` is an OpenAI-compatible alias for Zen Go."""
    cfg = _cfg(
        model="kimi-k2.7-code",
        provider=ProviderConfig(name="opencode"),
        api_key_env="OPENCODE_API_KEY",
    )
    model = build_model(cfg)
    assert str(model.provider.base_url).startswith(  # type: ignore[attr-defined]
        "https://opencode.ai/zen/go/v1"
    )
    headers = model.provider.client._custom_headers  # type: ignore[attr-defined]
    assert headers.get("x-opencode-session"), "needs stable session header"
    assert "mysharedbrain" in headers.get("User-Agent", "")


def test_build_model_opencode_go_alias_matches() -> None:
    """Docs use `opencode-go/<model>`; accept it too."""
    cfg = _cfg(
        model="kimi-k3",
        provider=ProviderConfig(name="opencode-go"),
    )
    model = build_model(cfg)
    assert str(model.provider.base_url).startswith(  # type: ignore[attr-defined]
        "https://opencode.ai/zen/go/v1"
    )


def test_build_model_with_no_provider_block_uses_the_model_string() -> None:
    """The simple path is unchanged: an empty provider block changes nothing."""
    model = build_model(_cfg(model="test"))
    assert model.model_name == "test"
    assert model_string(_cfg(model="openai:gpt-4o")) == "openai:gpt-4o"


def test_provider_name_prefixes_a_bare_model_id() -> None:
    """Pick `ollama` and type `llama3.1`: the string becomes `ollama:llama3.1`."""
    assert (
        model_string(
            BrainConfigDocument(
                agent=AgentConfig(
                    model="llama3.1", provider=ProviderConfig(name="ollama")
                )
            )
        )
        == "ollama:llama3.1"
    )
    # an explicit prefix wins, so nothing is double-prefixed
    assert (
        model_string(
            BrainConfigDocument(
                agent=AgentConfig(
                    model="openai:gpt-4o", provider=ProviderConfig(name="ollama")
                )
            )
        )
        == "openai:gpt-4o"
    )


def test_provider_catalog_reports_what_is_installed() -> None:
    """Dynamic: availability comes from trying to import the provider's SDK."""
    from mysharedbrain.agent import provider_catalog

    catalog = {info.name: info for info in provider_catalog()}
    assert catalog["openai"].available is True
    assert catalog["openai"].url_param == "base_url"
    # azure takes the endpoint under a different name — that is the whole reason
    # the mapping is read from the signature
    assert catalog["azure"].url_param == "azure_endpoint"
    assert catalog["azure"].api_version_param == "api_version"
    # sorted: usable providers first
    assert [i.available for i in provider_catalog() if i.name == "openai"] == [True]


def test_provider_catalog_marks_a_missing_sdk_unavailable() -> None:
    from mysharedbrain.agent import provider_catalog

    missing = [info for info in provider_catalog() if not info.available]
    if not missing:  # pragma: no cover - everything installed
        pytest.skip("every candidate SDK is installed here")
    assert all(info.hint for info in missing), "a missing SDK needs an install hint"


def test_check_model_uses_the_configured_endpoint() -> None:
    """A green line must reflect the endpoint, not just the model string."""

    async def fake(_model: object) -> str:
        return "ok"

    cfg = _cfg(
        model="qwen2.5",
        provider=ProviderConfig(name="ollama", base_url="http://localhost:11434/v1"),
    )
    check = asyncio.run(check_model(cfg, run=fake))
    assert check.ok is True
    assert check.name == "qwen2.5"


def test_check_model_reports_a_missing_provider_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not installed is a red line with the install hint, not a crash."""

    def explode(_name: str) -> type[Any]:
        raise ImportError("Please install the `anthropic` package to use it")

    monkeypatch.setattr("mysharedbrain.agent._provider_class", explode)
    cfg = BrainConfigDocument(
        agent=AgentConfig(model="claude-3-5", provider=ProviderConfig(name="anthropic"))
    )
    check = asyncio.run(check_model(cfg))
    assert check.ok is False
    assert "Please install the `anthropic` package" in check.detail


def _model_settings(agent: Agent[Any, Any]) -> ModelSettings:
    """The agent's settings as a mapping (pydantic-ai also allows a callable)."""
    return cast("ModelSettings", agent.model_settings)


def test_build_agent_applies_the_configured_temperature(vault_dir: Path) -> None:
    """The default has to reach the model, not just the config object."""
    agent = build_agent(BrainConfigDocument(), _lib(vault_dir), model=TEST_MODEL)
    assert _model_settings(agent).get("temperature") == 0.2


def test_build_agent_defers_when_temperature_is_null(vault_dir: Path) -> None:
    cfg = BrainConfigDocument(agent=AgentConfig(temperature=None))
    agent = build_agent(cfg, _lib(vault_dir), model=TEST_MODEL)
    assert "temperature" not in _model_settings(agent)


def test_build_agent_rejects_unknown_tool(vault_dir: Path) -> None:
    cfg = BrainConfig(tools={"nuke": ToolConfig()})
    with pytest.raises(ValueError, match="unknown tool"):
        build_agent(cfg, _lib(vault_dir), model=TEST_MODEL)


def test_build_agent_reports_missing_api_key(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = BrainConfig(agent=AgentConfig(model="openai:gpt-4o-mini"))
    with pytest.raises(ValueError, match="cannot use model"):
        build_agent(cfg, _lib(vault_dir))


def test_literal_api_key_is_exported_to_env(
    vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # setenv (not delenv) so monkeypatch removes the value the code writes.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    cfg = BrainConfig(agent=AgentConfig(api_key="sk-test"))
    build_agent(cfg, _lib(vault_dir), model=TEST_MODEL)
    assert os.environ["OPENAI_API_KEY"] == "sk-test"


def test_mcp_toolsets_honour_enabled_flag(vault_dir: Path) -> None:
    from mysharedbrain.agent import build_mcp_toolsets

    cfg = BrainConfig(
        mcp_servers=[
            MCPServerConfig(name="on", url="http://h/mcp"),
            MCPServerConfig(name="off", url="http://h/mcp", enabled=False),
        ]
    )
    assert [t.id for t in build_mcp_toolsets(cfg)] == ["on"]


async def test_run_agent_against_test_model(vault_dir: Path) -> None:
    """The pydantic-ai test model needs no key, so a full run can be verified."""
    cfg = BrainConfig(agent=AgentConfig(model="test"))
    outcome = await run_agent(cfg, _lib(vault_dir), "Do nothing.", model=TEST_MODEL)
    assert outcome.output == "noted"
    assert outcome.requests >= 1
