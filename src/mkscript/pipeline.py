"""Wire a GenerationRequest through a backend into a ScriptArtifact."""

from __future__ import annotations

import re

from .backend import Backend
from .contract import (
    GenerationRequest,
    ScriptArtifact,
    build_prompt,
    build_refine_prompt,
)
from .parser import parse_output


def _slug(text: str, *, max_words: int = 5) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:max_words]) or "script"


def generate(request: GenerationRequest, backend: Backend) -> ScriptArtifact:
    """Build the prompt, call the backend, and parse the reply into an artifact.

    The default filename stem is derived from the definition so that, when the
    model omits a filename, the parser still produces a meaningful name.
    """
    prompt = build_prompt(request)
    raw = backend.generate(prompt)
    return parse_output(raw, default_stem=_slug(request.definition))


def refine(
    request: GenerationRequest,
    previous: ScriptArtifact,
    change_request: str,
    backend: Backend,
) -> ScriptArtifact:
    """Regenerate a revised artifact from the current script and a change request.

    Mirrors generate's parse/failure behavior (an unusable reply still raises an
    OutputError), so the refine loop can surface failures rather than exiting.
    """
    prompt = build_refine_prompt(request, previous.source, change_request)
    raw = backend.generate(prompt)
    return parse_output(raw, default_stem=_slug(request.definition))
