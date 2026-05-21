"""Parse a backend's raw reply into a ScriptArtifact per the output contract.

The contract: a small flat JSON metadata object {language, filename} somewhere in
the prose, plus exactly one fenced code block holding the verbatim script. This
module enforces "exactly one block" and applies the fallback chain for language
and filename. Exhaustive failure-mode behavior and --refine surfacing are hardened
in WI-016; this is the core the contract requires.
"""

from __future__ import annotations

import json
import re

from .contract import ScriptArtifact


class OutputError(Exception):
    """Base class for unparseable model output."""


class NoScriptError(OutputError):
    """The reply contained no fenced code block (e.g. a refusal or prose only)."""


class AmbiguousOutputError(OutputError):
    """The reply contained more than one fenced code block."""


# A fenced code block: ```<info>\n<body>```
_FENCE_RE = re.compile(r"```([^\n]*)\n(.*?)\n?```", re.DOTALL)

# A flat JSON object — metadata is flat ({language, filename}), never nested.
_JSON_OBJ_RE = re.compile(r"\{[^{}]*\}")

# Language name -> file extension, for filename derivation.
_LANG_EXT = {
    "python": "py",
    "py": "py",
    "bash": "sh",
    "sh": "sh",
    "shell": "sh",
    "ruby": "rb",
    "javascript": "js",
    "node": "js",
    "typescript": "ts",
    "go": "go",
    "rust": "rs",
    "perl": "pl",
    "php": "php",
}

# Shebang interpreter -> language name.
_SHEBANG_LANG = {
    "python": "python",
    "python3": "python",
    "bash": "bash",
    "sh": "bash",
    "ruby": "ruby",
    "node": "javascript",
    "perl": "perl",
    "php": "php",
}


def _extract_metadata(prose: str) -> dict:
    """Return the first flat JSON object carrying language/filename, or {}."""
    for match in _JSON_OBJ_RE.finditer(prose):
        try:
            obj = json.loads(match.group(0))
        except ValueError:
            continue
        if isinstance(obj, dict) and ("language" in obj or "filename" in obj):
            return obj
    return {}


def _language_from_shebang(source: str) -> str | None:
    first = source.splitlines()[0] if source else ""
    if not first.startswith("#!"):
        return None
    tokens = first[2:].split()
    if not tokens:
        return None
    interp = tokens[0].rsplit("/", 1)[-1]
    if interp == "env" and len(tokens) > 1:
        interp = tokens[1].rsplit("/", 1)[-1]
    return _SHEBANG_LANG.get(interp)


def _derive_filename(language: str, stem: str) -> str:
    ext = _LANG_EXT.get(language.lower())
    return f"{stem}.{ext}" if ext else stem


def parse_output(raw: str, *, default_stem: str = "script") -> ScriptArtifact:
    """Parse a backend reply into a ScriptArtifact.

    Raises NoScriptError when there is no fenced block and AmbiguousOutputError
    when there is more than one. Language falls back metadata -> fence info ->
    shebang; filename falls back metadata -> derived from language + default_stem.
    """
    matches = list(_FENCE_RE.finditer(raw))
    if not matches:
        raise NoScriptError("model reply contained no fenced code block")
    if len(matches) > 1:
        raise AmbiguousOutputError(
            f"expected exactly one fenced code block, found {len(matches)}"
        )

    match = matches[0]
    info = match.group(1).strip()
    source = match.group(2)
    prose = raw[: match.start()] + raw[match.end() :]
    metadata = _extract_metadata(prose)

    language = (
        metadata.get("language")
        or (info or None)
        or _language_from_shebang(source)
        or ""
    )
    filename = metadata.get("filename") or _derive_filename(language, default_stem)
    return ScriptArtifact(language=language, filename=filename, source=source)
