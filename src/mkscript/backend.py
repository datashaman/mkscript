"""The swappable AI backend interface, plus a stub for tests.

A backend turns a prompt into the model's raw text reply. Prompt construction
(see contract.py) and output parsing (see parser.py) live outside the backend, so
a backend can be replaced — or implemented on top of a provider-abstraction
library — without touching generation logic. mkscript ships exactly one real
backend (WI-003); the stub here exists for tests and offline wiring.
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
