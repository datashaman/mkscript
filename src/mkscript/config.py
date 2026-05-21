"""Resolve which provider/model to use and how to authenticate to it.

This module owns the precedence rules for a run's configuration so the CLI seam
(cli.resolve_backend) stays thin. Two things are resolved:

* the ``provider:model`` id — from the ``--model`` flag, then ``MKSCRIPT_MODEL``,
  then a ``model`` key in the config file, then a built-in default; a model always
  resolves because the default backstops the chain.
* the API credential — from ``MKSCRIPT_API_KEY``, then an ``api_key`` key in the
  config file, then the provider-native variable (``ANTHROPIC_API_KEY`` /
  ``OPENAI_API_KEY``) that Pydantic-AI itself reads. When the credential lands in
  that last tier we hand ``None`` to the backend and let Pydantic-AI pick it up,
  preserving the documented "bring your own provider key" workflow.

When no credential can be found from any tier, resolution fails loudly and names
the specific environment variable the user is missing for the resolved provider.

The config file is TOML (parsed with the stdlib ``tomllib``, Python ≥ 3.11) and
lives in the OS-specific user config directory via ``platformdirs``. Everything is
injectable (``env``, ``config_path``) so resolution can be tested without touching
the real environment or filesystem, mirroring the CLI's injectable streams.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs

# Used when no flag, env var, or config file names a model. Kept in sync with the
# id the README advertises as a sensible starting point.
DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"

# mkscript's own override variables, checked above any provider-native key.
MODEL_ENV = "MKSCRIPT_MODEL"
API_KEY_ENV = "MKSCRIPT_API_KEY"

# The native credential variable Pydantic-AI reads for each shipped provider.
_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@dataclass(frozen=True)
class ResolvedConfig:
    """The settled configuration for a run.

    ``api_key`` is None when the credential comes from a provider-native variable;
    in that case the backend passes None through and Pydantic-AI resolves it.
    """

    model_id: str
    api_key: str | None


def default_config_path() -> Path:
    """Return the OS-specific config file path (``<user config dir>/config.toml``)."""
    return platformdirs.user_config_path("mkscript") / "config.toml"


def _load_config_file(path: Path) -> Mapping[str, object]:
    """Parse the TOML config file, treating a missing file as empty config."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SystemExit(f"could not read config file {str(path)!r}: {exc}")
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit(f"config file {str(path)!r} is not valid TOML: {exc}")


def _str_or_none(value: object, key: str, path: Path) -> str | None:
    """Coerce a config value to str, rejecting non-string entries loudly."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise SystemExit(f"config file {str(path)!r}: {key!r} must be a string")
    return value


def resolve_config(
    *,
    model_flag: str | None = None,
    env: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> ResolvedConfig:
    """Resolve model and credential by precedence; fail if no credential is found.

    Precedence for the model is flag → ``MKSCRIPT_MODEL`` → config ``model`` →
    built-in default. The credential is taken from ``MKSCRIPT_API_KEY`` → config
    ``api_key`` → the provider-native variable. With nothing in the first two
    credential tiers and the provider's native variable unset, this raises
    SystemExit naming that variable.
    """
    env = os.environ if env is None else env
    path = default_config_path() if config_path is None else config_path
    file_config = _load_config_file(path)

    model_id = (
        model_flag
        or env.get(MODEL_ENV)
        or _str_or_none(file_config.get("model"), "model", path)
        or DEFAULT_MODEL
    )

    explicit_key = env.get(API_KEY_ENV) or _str_or_none(
        file_config.get("api_key"), "api_key", path
    )
    if explicit_key:
        return ResolvedConfig(model_id=model_id, api_key=explicit_key)

    # Fall through to the provider-native variable that Pydantic-AI reads itself.
    provider = model_id.partition(":")[0]
    native_var = _PROVIDER_KEY_ENV.get(provider)
    if native_var is not None and env.get(native_var):
        return ResolvedConfig(model_id=model_id, api_key=None)

    missing = native_var or API_KEY_ENV
    raise SystemExit(
        f"no API credential found for provider {provider!r}: set {missing} (or "
        f"{API_KEY_ENV}), or add an 'api_key' to the config file at {str(path)!r}"
    )
