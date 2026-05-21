"""The command-line surface: parse arguments into a request, run, route output.

This module owns argument parsing, the stdin fallback for the definition, the
optional hints and context, and where the emitted script goes (stdout or --out).
It deliberately stays thin: the actual generation lives in pipeline.generate, the
bounded refine loop is wired in via a seam (WI-018), and provider/credential
resolution is wired in via resolve_backend (WI-021). Everything the CLI needs is
injectable so the surface can be exercised without a real model.
"""

from __future__ import annotations

import argparse
import platform
import sys
from collections.abc import Callable
from typing import IO

from .backend import Backend, PydanticAIBackend
from .config import resolve_config
from .contract import GenerationRequest, ScriptArtifact
from .parser import OutputError
from .pipeline import generate

# The seam for WI-018's bounded interactive refine loop. The CLI dispatches here
# under --refine; the callable is responsible for regenerating from change
# requests and emitting on accept.
RefineLoop = Callable[[GenerationRequest, Backend], None]


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
    refine_loop: RefineLoop | None = None,
) -> int:
    """Run the CLI. Injectable backend/streams/refine_loop keep the surface testable."""
    args = build_parser().parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout

    request = _request_from_args(args, stdin)
    if backend is None:
        backend = resolve_backend(args.model)

    if args.refine:
        # The refine loop owns its own generate calls, so OutputErrors surface
        # into the loop (WI-018) rather than exiting here.
        loop = refine_loop if refine_loop is not None else _default_refine_loop
        loop(request, backend)
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


def _default_refine_loop(request: GenerationRequest, backend: Backend) -> None:
    """Placeholder until WI-018 implements the bounded interactive refine loop."""
    raise SystemExit("the --refine interactive loop is not yet implemented (WI-018)")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
