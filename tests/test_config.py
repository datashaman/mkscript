import platformdirs
import pytest

from mkscript.config import (
    DEFAULT_MODEL,
    default_config_path,
    resolve_config,
)


def _write_config(tmp_path, body: str):
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


# --- model precedence: flag > MKSCRIPT_MODEL > config file > default ----------


def test_model_flag_wins_over_everything(tmp_path):
    path = _write_config(tmp_path, 'model = "config:model"\napi_key = "k"\n')
    config = resolve_config(
        model_flag="openai:gpt-4o",
        env={"MKSCRIPT_MODEL": "env:model", "MKSCRIPT_API_KEY": "k"},
        config_path=path,
    )
    assert config.model_id == "openai:gpt-4o"


def test_env_model_wins_over_config_and_default(tmp_path):
    path = _write_config(tmp_path, 'model = "config:model"\n')
    config = resolve_config(
        env={"MKSCRIPT_MODEL": "env:model", "MKSCRIPT_API_KEY": "k"},
        config_path=path,
    )
    assert config.model_id == "env:model"


def test_config_model_wins_over_default(tmp_path):
    path = _write_config(tmp_path, 'model = "anthropic:from-config"\napi_key = "k"\n')
    config = resolve_config(env={}, config_path=path)
    assert config.model_id == "anthropic:from-config"


def test_default_model_when_nothing_set(tmp_path):
    config = resolve_config(env={"MKSCRIPT_API_KEY": "k"}, config_path=tmp_path / "absent.toml")
    assert config.model_id == DEFAULT_MODEL


# --- credential sources: MKSCRIPT_API_KEY > config api_key > provider-native ---


def test_credential_from_mkscript_env(tmp_path):
    config = resolve_config(
        env={"MKSCRIPT_API_KEY": "from-env"},
        config_path=tmp_path / "absent.toml",
    )
    assert config.api_key == "from-env"


def test_credential_from_config_file_when_env_unset(tmp_path):
    path = _write_config(tmp_path, 'api_key = "from-file"\n')
    config = resolve_config(env={}, config_path=path)
    assert config.api_key == "from-file"


def test_provider_native_key_leaves_api_key_none_for_pydantic_ai(tmp_path):
    # Native var present: backend gets None and Pydantic-AI resolves it itself.
    config = resolve_config(
        model_flag="anthropic:claude-sonnet-4-6",
        env={"ANTHROPIC_API_KEY": "native"},
        config_path=tmp_path / "absent.toml",
    )
    assert config.api_key is None
    assert config.model_id == "anthropic:claude-sonnet-4-6"


# --- config file location is the platformdirs OS config dir -------------------


def test_default_config_path_under_platformdirs():
    path = default_config_path()
    assert path == platformdirs.user_config_path("mkscript") / "config.toml"


# --- unconfigured: exit non-zero naming the missing setting -------------------


def test_no_credential_exits_naming_provider_var(tmp_path):
    with pytest.raises(SystemExit) as exc:
        resolve_config(
            model_flag="anthropic:claude-sonnet-4-6",
            env={},
            config_path=tmp_path / "absent.toml",
        )
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_no_credential_for_openai_names_openai_var(tmp_path):
    with pytest.raises(SystemExit) as exc:
        resolve_config(model_flag="openai:gpt-4o", env={}, config_path=tmp_path / "absent.toml")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_unknown_provider_names_mkscript_var(tmp_path):
    # No native var known for the provider, so guidance falls back to MKSCRIPT_API_KEY.
    with pytest.raises(SystemExit) as exc:
        resolve_config(model_flag="cohere:command-r", env={}, config_path=tmp_path / "absent.toml")
    assert "MKSCRIPT_API_KEY" in str(exc.value)


# --- malformed config files fail loudly ---------------------------------------


def test_invalid_toml_exits(tmp_path):
    path = _write_config(tmp_path, "this is = = not toml")
    with pytest.raises(SystemExit, match="not valid TOML"):
        resolve_config(env={"MKSCRIPT_API_KEY": "k"}, config_path=path)


def test_non_string_config_value_exits(tmp_path):
    path = _write_config(tmp_path, "model = 123\napi_key = \"k\"\n")
    with pytest.raises(SystemExit, match="must be a string"):
        resolve_config(env={}, config_path=path)
