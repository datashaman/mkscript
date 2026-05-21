import pytest

from mkscript.parser import AmbiguousOutputError, NoScriptError, parse_output


def test_parses_metadata_and_block():
    raw = (
        '{"language": "python", "filename": "hello.py"}\n'
        "```python\n"
        'print("hi")\n'
        "```\n"
    )
    art = parse_output(raw)
    assert art.language == "python"
    assert art.filename == "hello.py"
    assert art.source == 'print("hi")'


def test_language_falls_back_to_fence_info():
    art = parse_output("```bash\necho hi\n```")
    assert art.language == "bash"
    assert art.filename == "script.sh"


def test_language_falls_back_to_shebang():
    art = parse_output("```\n#!/usr/bin/env python3\nprint(1)\n```")
    assert art.language == "python"
    assert art.filename.endswith(".py")


def test_filename_from_metadata_overrides_derivation():
    art = parse_output('{"filename": "run.sh"}\n```bash\necho hi\n```')
    assert art.filename == "run.sh"


def test_derived_filename_uses_stem():
    art = parse_output("```python\nprint(1)\n```", default_stem="rename-photos")
    assert art.filename == "rename-photos.py"


def test_malformed_metadata_falls_back():
    # Invalid JSON metadata is ignored; language comes from the fence info.
    art = parse_output("{language: python, filename}\n```python\nprint(1)\n```")
    assert art.language == "python"
    assert art.filename == "script.py"


def test_no_block_raises():
    with pytest.raises(NoScriptError):
        parse_output("I can't help with that.")


def test_multiple_blocks_raise():
    raw = "```python\n1\n```\nand also\n```python\n2\n```"
    with pytest.raises(AmbiguousOutputError):
        parse_output(raw)


def test_empty_block_raises_no_script():
    # A fenced block with only whitespace is not a usable script (hardening
    # beyond the explicit spec; "no usable block" covers it).
    with pytest.raises(NoScriptError, match="empty"):
        parse_output("```python\n   \n```")


def test_output_error_carries_the_raw_reply():
    raw = "I won't do that."
    with pytest.raises(NoScriptError) as exc:
        parse_output(raw)
    assert exc.value.raw == raw


def test_ambiguous_error_carries_the_raw_reply():
    raw = "```python\n1\n```\n```python\n2\n```"
    with pytest.raises(AmbiguousOutputError) as exc:
        parse_output(raw)
    assert exc.value.raw == raw
