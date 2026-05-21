"""Syntax-check a generated script before it is emitted.

Where mkscript ships a language-appropriate checker, the script is validated
before emission; a script that fails is surfaced rather than silently emitted
(see the CLI). Where no checker applies — an unsupported language, or the tool
is not installed — validation is skipped and emission proceeds best-effort.

Only static, never-execute checkers belong here: ``bash -n`` is a no-exec syntax
check and ``py_compile`` compiles without running module code, so validating a
script never executes it. ``perl -c`` is deliberately excluded — it runs BEGIN/END
blocks, which would execute model-influenced code.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .contract import ScriptArtifact

_CHECK_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of the pre-emit syntax check for one artifact.

    ``checker`` is the label of the checker that ran, or None when none applied
    (unsupported language or the tool is missing) — in which case emission is
    best-effort. ``passed`` is True when the checker accepted the script or when
    no checker ran. ``gated`` is True only when a checker ran and rejected it.
    """

    checker: str | None
    passed: bool
    diagnostics: str = ""

    @property
    def gated(self) -> bool:
        """True when a checker ran and rejected the script — block emission."""
        return self.checker is not None and not self.passed


@dataclass(frozen=True)
class _Checker:
    label: str
    suffix: str
    argv: Callable[[str], list[str]]


_CHECKERS: dict[str, _Checker] = {
    lang: _Checker("py_compile", ".py", lambda p: [sys.executable, "-m", "py_compile", p])
    for lang in ("python", "py")
} | {
    lang: _Checker("bash -n", ".sh", lambda p: ["bash", "-n", p])
    for lang in ("bash", "sh", "shell")
}

# Skipped result reused whenever no checker applies (unsupported language, missing
# tool, or a check that could not complete) — passed, with no checker recorded.
_SKIP = ValidationResult(checker=None, passed=True)


def validate_script(artifact: ScriptArtifact) -> ValidationResult:
    """Run the language-appropriate syntax checker, or skip when none applies."""
    checker = _CHECKERS.get(artifact.language.strip().lower())
    if checker is None:
        return _SKIP
    return _run_checker(checker, artifact.source)


def _run_checker(checker: _Checker, source: str) -> ValidationResult:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"script{checker.suffix}"
        path.write_text(source, encoding="utf-8")
        try:
            proc = subprocess.run(
                checker.argv(str(path)),
                capture_output=True,
                text=True,
                timeout=_CHECK_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            # The checker tool is not installed: no gate, emit best-effort.
            return _SKIP
        except subprocess.TimeoutExpired:
            return _SKIP
    if proc.returncode == 0:
        return ValidationResult(checker=checker.label, passed=True)
    diagnostics = (proc.stderr or proc.stdout or "").strip()
    return ValidationResult(checker=checker.label, passed=False, diagnostics=diagnostics)
