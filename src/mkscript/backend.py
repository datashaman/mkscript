"""The swappable AI backend interface, plus a stub for tests.

A backend turns a prompt into the model's raw text reply. Prompt construction
(see contract.py) and output parsing (see parser.py) live outside the backend, so
a backend can be replaced — or implemented on top of a provider-abstraction
library — without touching generation logic. mkscript ships exactly one real
backend, PydanticAIBackend; StubBackend exists for tests and offline wiring.
"""

from __future__ import annotations

from typing import Protocol


class Backend(Protocol):
    """Turns a prompt into the model's raw text reply."""

    def generate(self, prompt: str) -> str: ...


class StubBackend:
    """A backend that returns a fixed reply, for tests and offline wiring."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, prompt: str) -> str:  # noqa: ARG002 - prompt unused by design
        return self._reply


def _build_model(model_id: str, api_key: str | None):
    """Resolve a 'provider:model' id into a value that Agent() accepts.

    With no api_key, return the id string and let Pydantic-AI resolve the provider
    and key from the environment. With an explicit api_key (e.g. one mkscript read
    from its config file per WI-021), construct the provider object directly —
    supported for the shipped providers, anthropic and openai.
    """
    if api_key is None:
        return model_id
    provider, _, name = model_id.partition(":")
    if not name:
        raise ValueError(f"model id must be 'provider:model', got {model_id!r}")
    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(name, provider=AnthropicProvider(api_key=api_key))
    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(name, provider=OpenAIProvider(api_key=api_key))
    raise ValueError(
        f"an explicit api_key is only supported for the 'anthropic' and 'openai' "
        f"providers; got {provider!r}. Supply this provider's key via its "
        f"environment variable instead."
    )


class PydanticAIBackend:
    """The shipped backend: calls a model through Pydantic-AI.

    model_id is a 'provider:model' string (e.g. 'anthropic:claude-sonnet-4-6',
    'openai:gpt-4o'). Pydantic-AI is imported lazily so the core package and its
    tests do not require it unless this backend is actually constructed.
    """

    def __init__(self, model_id: str, *, api_key: str | None = None) -> None:
        from pydantic_ai import Agent

        self._agent = Agent(_build_model(model_id, api_key))

    def generate(self, prompt: str) -> str:
        return self._agent.run_sync(prompt).output
