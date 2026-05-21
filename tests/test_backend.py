import pytest

from mkscript.backend import PydanticAIBackend, _build_model


def test_build_model_returns_id_string_without_key():
    # No key: hand the id straight to Pydantic-AI for env-based resolution.
    assert _build_model("anthropic:claude-sonnet-4-6", None) == "anthropic:claude-sonnet-4-6"


def test_build_model_constructs_anthropic_with_key():
    from pydantic_ai.models.anthropic import AnthropicModel

    model = _build_model("anthropic:claude-sonnet-4-6", "test-key")
    assert isinstance(model, AnthropicModel)


def test_build_model_constructs_openai_with_key():
    from pydantic_ai.models.openai import OpenAIChatModel

    model = _build_model("openai:gpt-4o", "test-key")
    assert isinstance(model, OpenAIChatModel)


def test_build_model_rejects_unknown_provider_with_key():
    with pytest.raises(ValueError, match="anthropic.*openai"):
        _build_model("cohere:command-r", "test-key")


def test_build_model_rejects_malformed_id_with_key():
    with pytest.raises(ValueError, match="provider:model"):
        _build_model("just-a-model", "test-key")


def test_generate_returns_model_output():
    from pydantic_ai.models.test import TestModel

    # A dummy key lets the provider construct offline; override swaps in a
    # TestModel for the actual run, so no network/credentials are used.
    backend = PydanticAIBackend("openai:gpt-4o", api_key="test-key")
    with backend._agent.override(model=TestModel(custom_output_text="SCRIPT")):
        assert backend.generate("anything") == "SCRIPT"
