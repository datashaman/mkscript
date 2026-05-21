import io

from mkscript.cli import RefineSession, _default_refine_loop, main
from mkscript.contract import GenerationRequest


def _reply(source: str, *, language: str = "python", filename: str = "out.py") -> str:
    """A backend reply satisfying the output contract: metadata line + one block."""
    return f'{{"language": "{language}", "filename": "{filename}"}}\n```{language}\n{source}\n```'


REFUSAL = "I'm sorry, I can't help with that."


class ScriptedBackend:
    """Returns queued replies in order (repeating the last), recording each prompt."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self._replies) - 1)
        return self._replies[index]


def _session(replies, inputs, *, max_iterations=10, definition="say hi"):
    backend = ScriptedBackend(replies)
    stdin = io.StringIO("".join(f"{line}\n" for line in inputs))
    stderr = io.StringIO()
    emitted: list = []
    session = RefineSession(
        request=GenerationRequest(definition=definition, platform="linux"),
        backend=backend,
        stdin=stdin,
        stderr=stderr,
        emit=emitted.append,
        max_iterations=max_iterations,
    )
    return session, backend, stderr, emitted


def test_change_request_produces_revised_script_then_accept_emits():
    session, backend, _stderr, emitted = _session(
        [_reply("print('hi')"), _reply("print(f'hi {name}')")],
        ["greet by name", ":accept"],
    )
    _default_refine_loop(session)
    assert len(emitted) == 1
    assert emitted[0].source == "print(f'hi {name}')"  # the revised script is emitted
    # The refine call reuses the original definition and the prior script as context.
    refine_prompt = backend.prompts[1]
    assert "say hi" in refine_prompt
    assert "print('hi')" in refine_prompt
    assert "greet by name" in refine_prompt


def test_accept_immediately_emits_initial_script():
    session, backend, _stderr, emitted = _session([_reply("print('hi')")], [":accept"])
    _default_refine_loop(session)
    assert len(emitted) == 1
    assert emitted[0].source == "print('hi')"
    assert len(backend.prompts) == 1  # no regeneration happened


def test_empty_input_ends_without_emitting():
    session, _backend, _stderr, emitted = _session([_reply("print('hi')")], [""])
    _default_refine_loop(session)
    assert emitted == []


def test_quit_ends_without_emitting():
    session, _backend, _stderr, emitted = _session([_reply("print('hi')")], [":quit"])
    _default_refine_loop(session)
    assert emitted == []


def test_eof_ends_without_emitting():
    # stdin with no lines: readline() returns "" immediately.
    session, _backend, _stderr, emitted = _session([_reply("print('hi')")], [])
    _default_refine_loop(session)
    assert emitted == []


def test_loop_is_bounded_by_max_iterations():
    session, backend, stderr, emitted = _session(
        [_reply("v0"), _reply("v1"), _reply("v2")],
        ["a", "b", "c"],  # third change request should hit the cap
        max_iterations=2,
    )
    _default_refine_loop(session)
    assert emitted == []
    assert "maximum of 2" in stderr.getvalue()
    # initial + exactly 2 refines = 3 backend calls, no more.
    assert len(backend.prompts) == 3


def test_failed_generation_surfaces_then_course_corrects():
    session, backend, stderr, emitted = _session(
        [REFUSAL, _reply("print('hello')")],
        ["actually, write a hello script", ":accept"],
    )
    _default_refine_loop(session)
    assert "could not parse" in stderr.getvalue()  # refusal surfaced into the loop
    assert len(emitted) == 1
    assert emitted[0].source == "print('hello')"
    # After a failed initial generation the next input course-corrects via a fresh
    # generate (not a refine), carried as added context.
    assert "actually, write a hello script" in backend.prompts[1]


def test_accept_with_nothing_generated_yet_is_rejected():
    session, _backend, stderr, emitted = _session([REFUSAL], [":accept", ":quit"])
    _default_refine_loop(session)
    assert emitted == []
    assert "nothing to accept" in stderr.getvalue()


def test_main_wires_session_and_routes_emit_to_stdout():
    backend = ScriptedBackend([_reply("print('hi')")])
    out, err = io.StringIO(), io.StringIO()
    rc = main(
        ["say hi", "--refine"],
        backend=backend,
        stdin=io.StringIO(":accept\n"),
        stdout=out,
        stderr=err,
    )
    assert rc == 0
    assert "print('hi')" in out.getvalue()  # accepted script routed to stdout
    assert "refine, :accept, or :quit" in err.getvalue()  # prompts went to stderr


def test_main_refine_routes_accepted_script_to_out_file(tmp_path):
    dest = tmp_path / "build.py"
    backend = ScriptedBackend([_reply("print('hi')")])
    out, err = io.StringIO(), io.StringIO()
    rc = main(
        ["say hi", "--refine", "--out", str(dest)],
        backend=backend,
        stdin=io.StringIO(":accept\n"),
        stdout=out,
        stderr=err,
    )
    assert rc == 0
    assert "print('hi')" in dest.read_text()  # accepted script routed to --out
    assert out.getvalue() == ""  # nothing leaks to stdout when --out is given
