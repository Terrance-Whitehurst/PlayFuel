"""Tests for the LLM provider factory — Phase 6 / Task #9.

get_llm_provider() selection logic:
    - "auto" with no keys → TemplateProvider
    - "template" explicitly → TemplateProvider
    - "anthropic" without SDK → NotImplementedError
    - "openai" without SDK → NotImplementedError
    - "auto" with Anthropic key but no SDK → falls back to TemplateProvider (logged warning)
    - "auto" with OpenAI key but no SDK → falls back to TemplateProvider (logged warning)
"""
from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from playfuel_api.services.llm import AnthropicProvider, TemplateProvider, get_llm_provider


# ── Helpers ────────────────────────────────────────────────────────────────────

def _settings_with(
    *,
    llm_provider: str = "auto",
    anthropic_key: str = "",
    openai_key: str = "",
) -> object:
    """Return a minimal settings-like object for patching get_settings()."""
    class _FakeSettings:
        llm_provider = "auto"
        anthropic_api_key = ""
        anthropic_model = "claude-haiku-v3"
        openai_api_key = ""
        openai_model = "gpt-4o-mini"
        llm_max_tokens = 600
        llm_temperature = 0.3

    s = _FakeSettings()
    s.llm_provider = llm_provider
    s.anthropic_api_key = anthropic_key
    s.openai_api_key = openai_key
    return s


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_factory_returns_template_when_auto_no_keys() -> None:
    """get_llm_provider() returns TemplateProvider when LLM_PROVIDER=auto, no keys set."""
    with patch("playfuel_api.settings.get_settings", return_value=_settings_with()):
        provider = get_llm_provider()
    assert isinstance(provider, TemplateProvider)


def test_factory_returns_template_when_explicit_template() -> None:
    """get_llm_provider() returns TemplateProvider when LLM_PROVIDER=template."""
    with patch(
        "playfuel_api.settings.get_settings",
        return_value=_settings_with(llm_provider="template"),
    ):
        provider = get_llm_provider()
    assert isinstance(provider, TemplateProvider)


def test_factory_raises_not_implemented_for_anthropic_without_sdk() -> None:
    """get_llm_provider() raises NotImplementedError for anthropic without SDK.

    The anthropic SDK is not in pyproject.toml. Import will fail and the
    provider __init__ raises NotImplementedError with a clear install message.
    """
    from playfuel_api.services.llm import AnthropicProvider

    # Simulate missing SDK by patching the builtins import inside __init__
    import builtins
    real_import = builtins.__import__

    def _block_anthropic(name: str, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_block_anthropic):
        with pytest.raises(NotImplementedError, match="anthropic"):
            AnthropicProvider(api_key="test-key", model="claude-haiku-v3")


def test_factory_raises_not_implemented_for_openai_without_sdk() -> None:
    """get_llm_provider() raises NotImplementedError for openai without SDK."""
    from playfuel_api.services.llm import OpenAIProvider

    import builtins
    real_import = builtins.__import__

    def _block_openai(name: str, *args, **kwargs):
        if name == "openai":
            raise ImportError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_block_openai):
        with pytest.raises(NotImplementedError, match="openai"):
            OpenAIProvider(api_key="test-key", model="gpt-4o-mini")


def test_factory_falls_back_to_template_when_anthropic_key_set_but_sdk_missing() -> None:
    """auto mode: Anthropic key present but SDK missing → TemplateProvider fallback."""
    import builtins
    real_import = builtins.__import__

    def _block_anthropic(name: str, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    with (
        patch(
            "playfuel_api.settings.get_settings",
            return_value=_settings_with(
                llm_provider="auto",
                anthropic_key="sk-ant-test",
            ),
        ),
        patch("builtins.__import__", side_effect=_block_anthropic),
    ):
        provider = get_llm_provider()

    assert isinstance(provider, TemplateProvider), (
        "Expected TemplateProvider fallback when Anthropic key is set but SDK missing"
    )


def test_factory_falls_back_to_template_when_openai_key_set_but_sdk_missing() -> None:
    """auto mode: OpenAI key present but SDK missing → TemplateProvider fallback."""
    import builtins
    real_import = builtins.__import__

    def _block_openai(name: str, *args, **kwargs):
        if name in ("openai",):
            raise ImportError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    with (
        patch(
            "playfuel_api.settings.get_settings",
            return_value=_settings_with(
                llm_provider="auto",
                openai_key="sk-test",
            ),
        ),
        patch("builtins.__import__", side_effect=_block_openai),
    ):
        provider = get_llm_provider()

    assert isinstance(provider, TemplateProvider), (
        "Expected TemplateProvider fallback when OpenAI key is set but SDK missing"
    )


def test_factory_returns_anthropic_provider_when_sdk_installed_and_key_set() -> None:
    """AC-LLM-9: LLM_PROVIDER=anthropic + key set + SDK installed → AnthropicProvider.

    Now that 'anthropic>=0.40' is a declared dependency, the SDK is available.
    Factory must return AnthropicProvider (not TemplateProvider) when explicitly
    requested with a valid key.
    """
    with patch(
        "playfuel_api.settings.get_settings",
        return_value=_settings_with(
            llm_provider="anthropic",
            anthropic_key="sk-ant-test",
        ),
    ):
        provider = get_llm_provider()

    assert isinstance(provider, AnthropicProvider), (
        f"Expected AnthropicProvider when SDK installed + key set. Got: {type(provider).__name__}"
    )
