import io
import platform

import pytest

from mkscript import cli
from mkscript.backend import StubBackend
from mkscript.cli import main

# A backend reply that satisfies the output contract: one metadata line + one block.
REPLY = '{"language": "python", "filename": "hi.py"}\n```python\nprint("hi")\n```'


class _PipeStdin(io.StringIO):
    """StringIO that reports as a pipe (not a TTY), so the stdin fallback reads it."""

    def isatty(self) -> bool:
        return False


class _TTYStdin(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_definition_from_positional():
    out = io.StringIO()
    rc = main(["say hi"], backend=StubBackend(REPLY), stdout=out)
    assert rc == 0
    assert 'print("hi")' in out.getvalue()


def test_definition_from_stdin_when_positional_absent():
    captured = {}

    def fake_loop(request, backend):  # not used; single-shot path here
        captured["request"] = request

    out = io.StringIO()
    rc = main([], backend=StubBackend(REPLY), stdin=_PipeStdin("say hi"), stdout=out)
    assert rc == 0
    assert 'print("hi")' in out.getvalue()


def test_no_definition_and_tty_exits_nonzero():
    with pytest.raises(SystemExit):
        main([], backend=StubBackend(REPLY), stdin=_TTYStdin(""), stdout=io.StringIO())


def test_empty_stdin_exits_nonzero():
    with pytest.raises(SystemExit):
        main([], backend=StubBackend(REPLY), stdin=_PipeStdin("   "), stdout=io.StringIO())


def test_lang_and_platform_flow_into_request():
    seen = {}
    main(
        ["task", "--lang", "python", "--platform", "linux", "--refine"],
        backend=StubBackend(REPLY),
        refine_loop=lambda req, be: seen.setdefault("req", req),
    )
    assert seen["req"].language_hint == "python"
    assert seen["req"].platform == "linux"


def test_platform_defaults_to_host_os_when_omitted():
    seen = {}
    main(
        ["task", "--refine"],
        backend=StubBackend(REPLY),
        refine_loop=lambda req, be: seen.setdefault("req", req),
    )
    assert seen["req"].platform == platform.system().lower()


def test_context_string_populates_request():
    seen = {}
    main(
        ["task", "--context", "input is a CSV", "--refine"],
        backend=StubBackend(REPLY),
        refine_loop=lambda req, be: seen.setdefault("req", req),
    )
    assert seen["req"].context == "input is a CSV"


def test_context_file_populates_request(tmp_path):
    ctx = tmp_path / "sample.csv"
    ctx.write_text("a,b,c\n1,2,3\n")
    seen = {}
    main(
        ["task", "--context-file", str(ctx), "--refine"],
        backend=StubBackend(REPLY),
        refine_loop=lambda req, be: seen.setdefault("req", req),
    )
    assert "a,b,c" in seen["req"].context


def test_context_and_context_file_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        main(
            ["task", "--context", "x", "--context-file", "y"],
            backend=StubBackend(REPLY),
            stdout=io.StringIO(),
        )


def test_neither_context_is_valid():
    seen = {}
    main(
        ["task", "--refine"],
        backend=StubBackend(REPLY),
        refine_loop=lambda req, be: seen.setdefault("req", req),
    )
    assert seen["req"].context is None


def test_output_goes_to_stdout_by_default():
    out = io.StringIO()
    main(["task"], backend=StubBackend(REPLY), stdout=out)
    assert 'print("hi")' in out.getvalue()


def test_output_written_to_out_file(tmp_path):
    dest = tmp_path / "build.py"
    out = io.StringIO()
    main(["task", "--out", str(dest)], backend=StubBackend(REPLY), stdout=out)
    assert 'print("hi")' in dest.read_text()
    assert out.getvalue() == ""  # nothing on stdout when routed to a file


def test_without_refine_runs_single_shot_not_loop():
    called = {"loop": False}
    out = io.StringIO()
    main(
        ["task"],
        backend=StubBackend(REPLY),
        stdout=out,
        refine_loop=lambda req, be: called.__setitem__("loop", True),
    )
    assert called["loop"] is False
    assert 'print("hi")' in out.getvalue()


def test_with_refine_enters_loop_with_request_and_backend():
    called = {}
    backend = StubBackend(REPLY)
    main(
        ["task", "--refine"],
        backend=backend,
        refine_loop=lambda req, be: called.update(req=req, backend=be),
    )
    assert called["req"].definition == "task"
    assert called["backend"] is backend


def test_model_flag_reaches_resolve_backend(monkeypatch):
    # No injected backend, so main() goes through the resolution seam; capture
    # the flag there instead of touching real config/credentials.
    seen = {}

    def capture(model_flag=None):
        seen["model"] = model_flag
        return StubBackend(REPLY)

    monkeypatch.setattr(cli, "resolve_backend", capture)
    main(["task", "--model", "openai:gpt-4o"], stdout=io.StringIO())
    assert seen["model"] == "openai:gpt-4o"


# A reply that is a refusal (no fenced block) and one with two blocks.
REFUSAL = "I'm sorry, I can't help with that request."
TWO_BLOCKS = "```python\nprint(1)\n```\nand\n```python\nprint(2)\n```"


def test_refusal_exits_nonzero_and_shows_reply():
    with pytest.raises(SystemExit) as exc:
        main(["task"], backend=StubBackend(REFUSAL), stdout=io.StringIO())
    message = str(exc.value)
    assert "could not parse" in message
    assert REFUSAL in message  # the model's reply is shown to the user


def test_multiple_blocks_exit_nonzero():
    with pytest.raises(SystemExit) as exc:
        main(["task"], backend=StubBackend(TWO_BLOCKS), stdout=io.StringIO())
    assert "could not parse" in str(exc.value)


def test_parse_failure_surfaces_into_refine_loop_not_exit():
    # Under --refine the loop owns generation, so a bad reply must reach the loop
    # (where WI-018 will catch it) instead of exiting from main().
    reached = {}
    main(
        ["task", "--refine"],
        backend=StubBackend(REFUSAL),
        refine_loop=lambda req, be: reached.update(req=req, backend=be),
    )
    assert reached["req"].definition == "task"


def test_missing_credential_aborts_before_refine_loop(monkeypatch):
    # resolve_backend (the credential gate) runs before dispatch, so an
    # unconfigured run exits without ever entering the refine loop.
    def boom(model_flag=None):
        raise SystemExit("no API credential found")

    monkeypatch.setattr(cli, "resolve_backend", boom)
    loop_ran = {"yes": False}
    with pytest.raises(SystemExit, match="no API credential"):
        main(["task", "--refine"], refine_loop=lambda req, be: loop_ran.__setitem__("yes", True))
    assert loop_ran["yes"] is False
