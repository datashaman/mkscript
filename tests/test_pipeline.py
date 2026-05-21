from mkscript import GenerationRequest, generate
from mkscript.backend import StubBackend
from mkscript.contract import build_prompt


def test_generate_produces_artifact():
    reply = '{"language": "python", "filename": "hi.py"}\n```python\nprint("hi")\n```'
    art = generate(GenerationRequest(definition="say hi"), StubBackend(reply))
    assert art.language == "python"
    assert art.filename == "hi.py"
    assert 'print("hi")' in art.source


def test_generate_derives_filename_from_definition():
    reply = "```python\nprint(1)\n```"
    art = generate(
        GenerationRequest(definition="Convert a CSV to SQLite please"),
        StubBackend(reply),
    )
    assert art.filename == "convert-a-csv-to-sqlite.py"


def test_build_prompt_includes_hints_and_context():
    request = GenerationRequest(
        definition="resize images",
        context="input is a folder of PNGs",
        language_hint="python",
        platform="linux",
    )
    prompt = build_prompt(request)
    assert "resize images" in prompt
    assert "python" in prompt
    assert "linux" in prompt
    assert "input is a folder of PNGs" in prompt
    assert "exactly one fenced code block" in prompt.lower()
