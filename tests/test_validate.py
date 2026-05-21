import mkscript.validate as validate_mod
from mkscript.contract import ScriptArtifact
from mkscript.validate import validate_script


def _art(source: str, *, language: str = "python", filename: str = "x.py") -> ScriptArtifact:
    return ScriptArtifact(language=language, filename=filename, source=source)


def test_valid_python_passes():
    result = validate_script(_art("print('hi')\n"))
    assert result.checker == "py_compile"
    assert result.passed
    assert not result.gated


def test_invalid_python_is_gated_with_diagnostics():
    result = validate_script(_art("def f(:\n"))
    assert result.checker == "py_compile"
    assert not result.passed
    assert result.gated
    assert result.diagnostics  # the SyntaxError is surfaced, not swallowed


def test_language_label_is_normalized():
    # The model may emit "Python"; normalization still selects py_compile.
    result = validate_script(_art("print(1)\n", language="Python"))
    assert result.checker == "py_compile"
    assert result.passed


def test_valid_bash_passes():
    result = validate_script(_art("echo hi\n", language="bash", filename="x.sh"))
    assert result.checker == "bash -n"
    assert result.passed


def test_invalid_bash_is_gated():
    # Missing `fi` is an unexpected-EOF syntax error under bash -n.
    result = validate_script(_art("if true; then\n", language="bash", filename="x.sh"))
    assert result.checker == "bash -n"
    assert result.gated


def test_unsupported_language_is_skipped():
    result = validate_script(_art("(println 1)", language="clojure", filename="x.clj"))
    assert result.checker is None
    assert result.passed
    assert not result.gated


def test_empty_language_is_skipped():
    result = validate_script(_art("whatever", language="", filename="x"))
    assert result.checker is None
    assert result.passed


def test_missing_checker_tool_is_skipped(monkeypatch):
    # When the checker binary is absent, validation skips rather than crashing.
    def boom(*args, **kwargs):
        raise FileNotFoundError("no such tool")

    monkeypatch.setattr(validate_mod.subprocess, "run", boom)
    result = validate_script(_art("print(1)\n"))
    assert result.checker is None
    assert result.passed
