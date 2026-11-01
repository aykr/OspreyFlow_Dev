"""`ospreyflow models` (`06_DECISIONS.md` ADR-135 decision 3): the engines a deployment enables,
each role's default, and whether each provider's key is present; `models key <name>` sets or
rotates a key and `models remove-key <name>` removes it.

A key is entered in the terminal (`OSPREY_MODEL_KEY_<NAME>`) or at a hidden prompt, and written to
the deployment's `deployment.env` alone — never printed, never on a command line, never in
`osprey.yaml` or a generated file. Nothing rendered holds a key or depends on one: the gateway's
model table names each key by its variable, and the Conduit is told whether each is present by
Compose, from the same file, when it starts. So a change needs no render — only the services whose
environment changed are started again: the gateway (`litellm`), which reads the key, and the
Conduit (`api`), which Compose starts again only when the key's presence changed.

The command runs outside the checkout's own environment, so it reads `osprey.yaml` as plain data and
names each key by the harness's rule (`schemas.deployment.ModelsConfig.key_variable`), held to it
by `tests/cli/test_models_verb.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from .home import CommandRefused

ROLES = ("extraction", "vision", "transcription", "embedding")
LOCAL = "local"
_LABELS = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Gemini"}
#: The services that read a model key, or whether one is present (`harness/render.py`).
RESTARTED = ("litellm", "api")


def _models(config: Mapping[str, Any]) -> dict[str, Any]:
    models = config.get("models")
    return models if isinstance(models, dict) else {}


def _providers(models: Mapping[str, Any]) -> list[dict[str, Any]]:
    single = models.get("provider")
    if isinstance(single, dict):
        return [single]
    return [p for p in models.get("providers") or [] if isinstance(p, dict)]


def key_variable(models: Mapping[str, Any], provider: str) -> str:
    """Where a provider's key is kept: `OSPREY_MODEL_KEY_<NAME>`, or `OSPREY_MODEL_PROVIDER_KEY`
    for the single `models.provider` (ADR-135 decision 2)."""
    if isinstance(models.get("provider"), dict):
        return "OSPREY_MODEL_PROVIDER_KEY"
    return f"OSPREY_MODEL_KEY_{provider.upper()}"


def _label(provider: Mapping[str, Any]) -> str:
    name = str(provider.get("name", ""))
    return str(provider.get("label") or _LABELS.get(name) or name.replace("_", " ").title())


def _defaults(models: Mapping[str, Any]) -> dict[str, str]:
    named = models.get("defaults")
    if isinstance(named, dict) and named:
        return {str(r): str(e) for r, e in named.items()}
    single = models.get("provider")
    if isinstance(single, dict):
        return {str(r): str(single.get("name")) for r in single.get("roles") or {}}
    return {}


def _env_lines(env_file: Path) -> list[str]:
    return env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []


def _held(env_file: Path) -> dict[str, str]:
    held: dict[str, str] = {}
    for line in _env_lines(env_file):
        name, sep, value = line.partition("=")
        if sep and not line.startswith("#"):
            held[name] = value
    return held


def read_models(product: Path, deployment: Path) -> dict[str, Any]:
    """The deployment's own copy of `osprey.yaml` (what is running), else the product's."""
    for candidate in (deployment / "osprey.yaml", product / "osprey.yaml"):
        if candidate.is_file():
            loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                return _models(loaded)
    return {}


def list_engines(models: Mapping[str, Any], env_file: Path) -> list[str]:
    """What `ospreyflow models` says: each engine, whether each key is present (yes or no, never
    the key), and each role's default."""
    held = _held(env_file)
    lines = ["Engines:", f"  {LOCAL}: this deployment's own models (no key)"]
    for provider in _providers(models):
        name = str(provider.get("name"))
        present = "yes" if held.get(key_variable(models, name)) else "no"
        roles = ", ".join(f"{r} {m}" for r, m in (provider.get("roles") or {}).items())
        lines.append(f"  {name} ({_label(provider)}): key present: {present} — {roles}")
    defaults = _defaults(models)
    lines.append("Defaults:")
    lines += [f"  {role}: {defaults.get(role, LOCAL)}" for role in ROLES]
    if not _providers(models):
        lines.append("No provider is enabled: every role runs on this deployment's own models.")
    return lines


def _provider(models: Mapping[str, Any], name: str) -> dict[str, Any]:
    for provider in _providers(models):
        if provider.get("name") == name:
            return provider
    enabled = ", ".join(str(p.get("name")) for p in _providers(models)) or "none"
    raise CommandRefused(
        f"{name} is not a provider this deployment enables (enabled: {enabled}). Enable it under "
        "models.providers in osprey.yaml and run ospreyflow install again; the local engine has "
        "no key."
    )


def _write(env_file: Path, variable: str, value: str | None) -> bool:
    """`variable`'s line set to `value` (appended where absent), or removed when `value` is None;
    every other line as it was. The file is written in place, so its mode is kept. Whether
    anything changed."""
    lines = _env_lines(env_file)
    kept: list[str] = []
    found = False
    for line in lines:
        name, sep, _ = line.partition("=")
        if sep and not line.startswith("#") and name == variable:
            if value is not None and not found:
                kept.append(f"{variable}={value}")
            found = True
            continue
        kept.append(line)
    if value is not None and not found:
        kept.append(f"{variable}={value}")
    if kept == lines:
        return False
    env_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return True


def set_key(
    models: Mapping[str, Any],
    name: str,
    env_file: Path,
    environ: Mapping[str, str],
    ask_secret: Callable[[str], str],
) -> str:
    """Writes the provider's key into `env_file`, from `OSPREY_MODEL_KEY_<NAME>` in the terminal
    (or the single provider's `OSPREY_MODEL_PROVIDER_KEY`), else a hidden prompt. Returns the
    label."""
    provider = _provider(models, name)
    variable = key_variable(models, name)
    terminal = f"OSPREY_MODEL_KEY_{name.upper()}"
    key = (environ.get(terminal) or environ.get(variable) or "").strip()
    if not key:
        key = ask_secret(f"Key for {_label(provider)} ({terminal}; not shown): ").strip()
    if not key:
        raise CommandRefused(f"No key was given for {_label(provider)}; nothing was changed.")
    if any(ch.isspace() for ch in key) or "\n" in key:
        raise CommandRefused("A key has no spaces or line breaks in it; nothing was changed.")
    _write(env_file, variable, key)
    return _label(provider)


def remove_key(models: Mapping[str, Any], name: str, env_file: Path) -> tuple[str, bool]:
    """Removes the provider's key line. Returns the label and whether there was one."""
    provider = _provider(models, name)
    return _label(provider), _write(env_file, key_variable(models, name), None)
