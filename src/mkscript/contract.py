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
- The script must be a single self-contained file: no companion files, and no
  reliance on a separate install step. Any dependency outside the language's
  standard library MUST be declared inline using the language's idiom so the file
  runs as-is. For Python this means a PEP 723 inline-metadata block listing every
  non-stdlib import, e.g.:

      # /// script
      # dependencies = ["requests", "pandas"]
      # ///

  For bash, use only standard builtins and tools you can assume are present. If a
  language has no inline-dependency idiom, restrict yourself to its standard
  library.
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
    parts += _hint_lines(request)
    parts += ["", OUTPUT_CONTRACT]
    return "\n".join(parts)


def _hint_lines(request: GenerationRequest) -> list[str]:
    """The optional language/platform/context lines shared by both prompt builders."""
    parts: list[str] = []
    if request.language_hint:
        parts += ["", f"PREFERRED LANGUAGE (a hint, not a requirement): {request.language_hint}"]
    if request.platform:
        parts += ["", f"TARGET PLATFORM: {request.platform}"]
    if request.context:
        parts += ["", "CONTEXT (sample data / desired output format):", request.context.strip()]
    return parts


def build_refine_prompt(
    request: GenerationRequest, previous_source: str, change_request: str
) -> str:
    """Compose a revision prompt reusing the session's task/hints plus the change.

    The original task and hints are restated, the current script is shown verbatim,
    and the user's natural-language change request is appended. The same output
    contract applies, so the reply is parsed identically to a fresh generation.
    """
    parts: list[str] = [
        "Revise the script below to satisfy the change request. Keep it a single, "
        "self-contained file that still accomplishes the original task.",
        "",
        "ORIGINAL TASK:",
        request.definition.strip(),
    ]
    parts += _hint_lines(request)
    parts += [
        "",
        "CURRENT SCRIPT:",
        "```",
        previous_source,
        "```",
        "",
        "CHANGE REQUEST:",
        change_request.strip(),
        "",
        OUTPUT_CONTRACT,
    ]
    return "\n".join(parts)
