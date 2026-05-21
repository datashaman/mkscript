"""mkscript — compile a task definition into one self-contained script."""

from __future__ import annotations

from .cli import main
from .contract import GenerationRequest, ScriptArtifact, build_prompt
from .parser import (
    AmbiguousOutputError,
    NoScriptError,
    OutputError,
    parse_output,
)
from .pipeline import generate

__version__ = "0.0.1"

__all__ = [
    "GenerationRequest",
    "ScriptArtifact",
    "build_prompt",
    "generate",
    "main",
    "parse_output",
    "OutputError",
    "NoScriptError",
    "AmbiguousOutputError",
    "__version__",
]
