# mkscript

Compile a one-off task description into a single, self-contained, runnable script — using AI.

> **Status:** early / specification stage. The design is modeled in the growth MCP
> service (requirements, milestones, work items, verification, architecture); code
> has not landed yet. This README describes the intended v1.

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
  one backend ships.

## Intended CLI

```
mkscript "describe the task"            # script printed to stdout
mkscript "..." --out build.sh           # written to a file instead
echo "describe the task" | mkscript     # definition from stdin
mkscript "..." --lang python            # preferred-language hint
mkscript "..." --platform linux         # target platform (defaults to host OS)
mkscript "..." --context-file sample.csv  # optional context (sample data / format)
mkscript "..." --refine                 # interactive, bounded refine loop
```

Configuration (provider/model, credentials) resolves from `--model` flag → env
var → a config file in the OS-specific config directory (via `platformdirs`) →
built-in default. The API credential may come from an environment variable or
that config file.

## Stack

Python, distributed as a single-file tool (PEP 723) run via [uv](https://docs.astral.sh/uv/).

## License

MIT — see [LICENSE](LICENSE).
