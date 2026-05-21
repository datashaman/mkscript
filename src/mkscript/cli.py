"""The command-line surface: parse arguments into a request, run, route output.

This module owns argument parsing, the stdin fallback for the definition, the
optional hints and context, and where the emitted script goes (stdout or --out).
It deliberately stays thin: the actual generation lives in pipeline.generate, the
bounded interactive refine loop runs via a swappable seam (_default_refine_loop),
and provider/credential resolution lives in resolve_backend. Everything the CLI
needs is injectable so the surface can be exercised without a real model.
"""

from __future__ import annotations

import argparse
import dataclasses
import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO

from .backend import Backend, PydanticAIBackend
from .config import resolve_config
from .contract import GenerationRequest, ScriptArtifact
from .parser import OutputError
from .pipeline import generate, refine

# The default ceiling on refine rounds, counting every backend call past the
# initial generation, so a stream of refusals can never loop without bound.
MAX_REFINE_ITERATIONS = 10


@dataclass(frozen=True)
class RefineSession:
    """Everything the bounded interactive refine loop needs, all injectable.

    ``emit`` routes an accepted artifact to its final destination (stdout or the
    --out file); interactive prompts and interim scripts go to ``stderr`` so the
    emitted script keeps stdout to itself.
    """

    request: GenerationRequest
    backend: Backend
    stdin: IO[str]
    stderr: IO[str]
    emit: Callable[[ScriptArtifact], None]
    max_iterations: int = MAX_REFINE_ITERATIONS


# The seam for the bounded interactive refine loop. The CLI builds a RefineSession
# under --refine and dispatches here; the loop owns generation, regeneration from
# change requests, and emitting on accept.
RefineLoop = Callable[[RefineSession], None]


def resolve_backend(model_flag: str | None = None) -> Backend:
    """Construct the backend, resolving provider/model and credential by precedence.

    Resolution (and the unconfigured-credential error path) lives in config.py;
    this seam just turns the settled choice into a concrete backend.
    """
    config = resolve_config(model_flag=model_flag)
    return PydanticAIBackend(config.model_id, api_key=config.api_key)


def build_parser() -> argparse.ArgumentParser:
    """Define the mkscript command-line interface."""
    parser = argparse.ArgumentParser(
        prog="mkscript",
        description="Compile a task description into one self-contained script.",
    )
    parser.add_argument(
        "definition",
        nargs="?",
        help="the task to compile into a script; read from stdin when omitted",
    )
    parser.add_argument(
        "--model",
        dest="model",
        help="provider:model id to use (e.g. anthropic:claude-sonnet-4-6); "
        "overrides MKSCRIPT_MODEL, the config file, and the built-in default",
    )
    parser.add_argument(
        "--lang",
        dest="lang",
        help="preferred language hint for the generated script (the model may honour it)",
    )
    parser.add_argument(
        "--platform",
        dest="platform",
        help="target platform hint; defaults to the detected host OS",
    )
    context = parser.add_mutually_exclusive_group()
    context.add_argument(
        "--context",
        dest="context",
        help="optional context (e.g. sample data or desired output format)",
    )
    context.add_argument(
        "--context-file",
        dest="context_file",
        help="path to a file whose contents are used as optional context",
    )
    parser.add_argument(
        "--out",
        dest="out",
        help="write the generated script to this file instead of stdout",
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="enter the bounded interactive refine loop after generation",
    )
    return parser


def _read_definition(positional: str | None, stdin: IO[str]) -> str:
    """Return the definition from the positional arg, falling back to stdin.

    With no positional arg and an interactive stdin (a TTY, nothing piped), there
    is nothing to read, so this fails loudly rather than blocking on input.
    """
    if positional is not None:
        return positional
    if stdin.isatty():
        raise SystemExit(
            "no task definition given: pass it as an argument or pipe it on stdin"
        )
    text = stdin.read().strip()
    if not text:
        raise SystemExit("no task definition given: stdin was empty")
    return text


def _request_from_args(args: argparse.Namespace, stdin: IO[str]) -> GenerationRequest:
    """Build a GenerationRequest from parsed args, reading context/definition I/O."""
    definition = _read_definition(args.definition, stdin)
    context = args.context
    if args.context_file is not None:
        try:
            with open(args.context_file, encoding="utf-8") as fh:
                context = fh.read()
        except OSError as exc:
            raise SystemExit(f"could not read --context-file {args.context_file!r}: {exc}")
    platform_hint = args.platform or platform.system().lower()
    return GenerationRequest(
        definition=definition,
        context=context,
        language_hint=args.lang,
        platform=platform_hint,
    )


def _emit(artifact: ScriptArtifact, out: str | None, stdout: IO[str]) -> None:
    """Route the generated script to stdout (default) or the --out file."""
    if out is None:
        stdout.write(artifact.source)
        if not artifact.source.endswith("\n"):
            stdout.write("\n")
        return
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(artifact.source)
        if not artifact.source.endswith("\n"):
            fh.write("\n")


def main(
    argv: list[str] | None = None,
    *,
    backend: Backend | None = None,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    refine_loop: RefineLoop | None = None,
) -> int:
    """Run the CLI. Injectable backend/streams/refine_loop keep the surface testable."""
    args = build_parser().parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr

    request = _request_from_args(args, stdin)
    if backend is None:
        backend = resolve_backend(args.model)

    if args.refine:
        # The refine loop owns its own generate calls, so OutputErrors surface
        # into the loop rather than exiting here.
        session = RefineSession(
            request=request,
            backend=backend,
            stdin=stdin,
            stderr=stderr,
            emit=lambda artifact: _emit(artifact, args.out, stdout),
        )
        loop = refine_loop if refine_loop is not None else _default_refine_loop
        loop(session)
        return 0

    try:
        artifact = generate(request, backend)
    except OutputError as exc:
        raise SystemExit(_format_output_error(exc))
    _emit(artifact, args.out, stdout)
    return 0


def _format_output_error(exc: OutputError) -> str:
    """Compose the non-zero-exit message for an unusable reply, showing the reply.

    The model's verbatim reply is fenced by labeled delimiters so a refusal or
    stray prose is clearly the model's text, not mkscript's own error output.
    """
    message = f"could not parse the model's reply: {exc}"
    if not exc.raw:
        return message
    return f"{message}\n--- model reply ---\n{exc.raw}\n--- end reply ---"


def _show_script(artifact: ScriptArtifact, stderr: IO[str]) -> None:
    """Print the current candidate script to stderr so the user can judge it."""
    lines = artifact.source.count("\n") + 1
    stderr.write(f"\n--- {artifact.filename} ({artifact.language or 'unknown'}, {lines} lines) ---\n")
    stderr.write(artifact.source)
    if not artifact.source.endswith("\n"):
        stderr.write("\n")
    stderr.write("--- end script ---\n")


def _default_refine_loop(session: RefineSession) -> None:
    """Bounded interactive refinement: regenerate from change requests, emit on accept.

    Generates an initial script, then loops: show the candidate, read a line, and
    either emit (`:accept`), end without emitting (blank input, `:quit`, or EOF),
    or treat the line as a natural-language change request and regenerate using the
    prior script as context. An unusable model reply is shown and the user may
    retry or quit. Every backend call past the initial counts toward
    ``max_iterations``, so refusals cannot loop without bound.
    """
    stderr = session.stderr
    request = session.request
    artifact = _try_generate(lambda: generate(request, session.backend), stderr)

    iterations = 0
    while True:
        if artifact is not None:
            _show_script(artifact, stderr)
        stderr.write(f"[{iterations}/{session.max_iterations}] refine, :accept, or :quit > ")
        stderr.flush()
        line = session.stdin.readline()

        if line == "":  # EOF (e.g. stdin closed)
            stderr.write("\n(end of input — exiting without emitting)\n")
            return
        command = line.strip()
        if command == "" or command.lower() in (":quit", ":q"):
            stderr.write("(exiting without emitting)\n")
            return
        if command.lower() == ":accept":
            if artifact is None:
                stderr.write("nothing to accept yet — the last attempt produced no script.\n")
                continue
            session.emit(artifact)
            return

        if iterations >= session.max_iterations:
            stderr.write(
                f"reached the maximum of {session.max_iterations} refine iterations; "
                "exiting without emitting.\n"
            )
            return
        iterations += 1

        if artifact is None:
            # No script yet (the model refused/failed): treat the line as a
            # course-correction appended to the task context, and try afresh.
            request = dataclasses.replace(request, context=_append_context(request.context, command))
            artifact = _try_generate(lambda: generate(request, session.backend), stderr)
        else:
            current = artifact
            artifact = _try_generate(
                lambda: refine(request, current, command, session.backend), stderr
            )


def _try_generate(call: Callable[[], ScriptArtifact], stderr: IO[str]) -> ScriptArtifact | None:
    """Run a generation call, surfacing an unusable reply to stderr instead of raising."""
    try:
        return call()
    except OutputError as exc:
        stderr.write(_format_output_error(exc) + "\n")
        return None


def _append_context(existing: str | None, addition: str) -> str:
    """Append a course-correction line to any existing context."""
    return f"{existing}\n\n{addition}" if existing else addition


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
