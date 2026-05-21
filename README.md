# mkscript

Compile a one-off task description into a single, self-contained, runnable script — using AI.

> **Status:** early (v0.0.1, pre-alpha). The core pipeline has landed — CLI,
> swappable backend, config/credential resolution, output parsing, pre-emit
> syntax checking, and the bounded interactive refine loop — and is covered by
> tests. Interfaces may still change.

## What it does (one thing)

You give mkscript a natural-language definition of a task. It asks an AI backend
to produce **exactly one self-contained script** and emits it. mkscript does
**not** execute the script — the emitted file is the sole deliverable.

- **The model chooses the language.** mkscript does not hard-code bash or Python;
  the AI picks a platform-appropriate language/runtime. You may nudge it with
  optional hints.
- **One file, no companions.** Dependencies are satisfied from within the single
  file using the language's idiom (e.g. PEP 723 inline metadata for Python,
  standard-shell builtins for bash).
- **Validated before emit.** Where a syntax check exists for the chosen language
  (e.g. `bash -n`, `py_compile`), a script that fails it is not silently emitted.
- **Swappable backend.** Generation sits behind a thin, vendor-neutral interface;
  the one shipped backend uses [Pydantic-AI](https://ai.pydantic.dev/)
  (`pydantic-ai-slim[anthropic,openai]`), so you bring your own provider key and
  pick a model like `anthropic:claude-sonnet-4-6` or `openai:gpt-4o`.

## CLI

```
mkscript "describe the task"            # script printed to stdout
mkscript "..." --out build.sh           # written to a file instead
echo "describe the task" | mkscript     # definition from stdin
mkscript "..." --model openai:gpt-4o    # pick the provider:model
mkscript "..." --lang python            # preferred-language hint
mkscript "..." --platform linux         # target platform (defaults to host OS)
mkscript "..." --context "id,name"        # optional context inline (sample data / format)
mkscript "..." --context-file sample.csv  # optional context from a file
mkscript "..." --refine                 # interactive, bounded refine loop
```

`--context` and `--context-file` are mutually exclusive.

Before emitting, mkscript runs a language-appropriate syntax check where one
exists (`py_compile` for Python, `bash -n` for shell); a script that fails is
surfaced and not emitted. Languages without a shipped checker are emitted
best-effort.

With `--refine`, mkscript shows each candidate script (and its check status) and
prompts on stderr, so stdout stays clean for the final file. Type a natural-language
change to revise it, `:accept` to emit the current script, or `:quit` (or a blank
line) to exit without emitting. A script that failed its syntax check is not
emitted by `:accept`; use `:accept!` to emit it anyway. The loop is bounded by a
maximum number of rounds.

Configuration resolves by precedence. The **provider/model** is taken from the
`--model` flag → `MKSCRIPT_MODEL` → a `model` key in the config file → a built-in
default. The **API credential** is taken from `MKSCRIPT_API_KEY` → an `api_key`
key in the config file → the provider-native variable (`ANTHROPIC_API_KEY` /
`OPENAI_API_KEY`) that Pydantic-AI reads itself. With no credential resolvable,
mkscript exits non-zero and names the variable to set.

The config file is TOML at `<OS config dir>/mkscript/config.toml` (located via
[`platformdirs`](https://pypi.org/project/platformdirs/)):

```toml
model = "anthropic:claude-sonnet-4-6"
api_key = "sk-..."
```

## Stack

Python, packaged under `src/mkscript/` and run via [uv](https://docs.astral.sh/uv/)
(`uv tool install`). Note: the *single-file* constraint applies to the scripts
mkscript **generates**, not to mkscript's own source.

## License

MIT — see [LICENSE](LICENSE).
