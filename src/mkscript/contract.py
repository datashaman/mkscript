"""Generation request/result types and the model output contract.

The backend is asked to return a small JSON metadata object describing the script
followed by exactly one fenced code block holding the script verbatim. The script
never goes inside JSON (no whole-script escaping); the fenced block is the
portable, escaping-free channel for the source.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationRequest:
    """A request to compile one task definition into a single script."""

    definition: str
    context: str | None = None
    language_hint: str | None = None
    platform: str | None = None


@dataclass(frozen=True)
class ScriptArtifact:
    """The single self-contained script produced from a request."""

    language: str
    filename: str
    source: str


OUTPUT_CONTRACT = """\
Respond with two parts, in order:

1. A single-line JSON object describing the script, with exactly these keys:
   {"language": "<language name>", "filename": "<suggested filename with extension>"}
   Keep the values short. Do not wrap this JSON in a code fence.

2. Exactly ONE fenced code block containing the complete script verbatim:

   ```<language>
   <the entire script>
   ```

Rules:
- Produce exactly one fenced code block — the script — and nothing else fenced.
- The script must be a single self-contained file: no companion files, with any
  dependencies declared inline using the language's idiom (e.g. PEP 723 metadata
  for Python; only standard builtins for bash).
- You choose the language; make it appropriate to the task and target platform.
- Any explanation outside the JSON and the code block is fine; it is shown but
  not saved.
"""


def build_prompt(request: GenerationRequest) -> str:
    """Compose the full instruction sent to the backend for one request."""
    parts: list[str] = [
        "Write a script that accomplishes the following task.",
        "",
        "TASK:",
        request.definition.strip(),
    ]
    if request.language_hint:
        parts += ["", f"PREFERRED LANGUAGE (a hint, not a requirement): {request.language_hint}"]
    if request.platform:
        parts += ["", f"TARGET PLATFORM: {request.platform}"]
    if request.context:
        parts += ["", "CONTEXT (sample data / desired output format):", request.context.strip()]
    parts += ["", OUTPUT_CONTRACT]
    return "\n".join(parts)
