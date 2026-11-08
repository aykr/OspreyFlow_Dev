"""`ospreyflow models` (`06_DECISIONS.md` ADR-135 decision 3, Amendment 2 decision 8): the engines
a deployment enables, each role's default, and each key's state; `models key <name>` sets or rotates
a key and `models remove-key <name>` removes it.

Since ADR-135 Amendment 2 a key lives in the model gateway's own database, put there by the
Conduit's key path (`services.api.model_keys`), which *Admin › Models* uses too, so the gateway's
admin API, the models file and the audit are one code. This command runs that path inside the
Conduit's container (`docker compose exec`), handing the key over by name in the Docker client's
environment (`-e OSPREY_MODEL_KEY_GIVEN`), never as an argument, never printed. Nothing is
restarted.
It works with the Glass unreachable or sign-in broken, which is what it is kept for.

The key is read in the terminal (`OSPREY_MODEL_KEY_<NAME>`) or at a hidden prompt. The command runs
outside the checkout's own environment, so it reads `osprey.yaml` as plain data and names each key
by the harness's rule (`schemas.deployment.ModelsConfig.key_variable`), held to it by
`tests/cli/test_models_verb.py`.
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
#: Where the key is handed to the Conduit's key path, by name (ADR-135 Amendment 2 decision 8).
KEY_GIVEN = "OSPREY_MODEL_KEY_GIVEN"
#: The Conduit's key path, run inside its container.
KEY_PATH = ("python", "-m", "services.api.model_keys")
_STATE_WORDS = {"set": "yes", "none": "no", "lost": "lost: enter it again"}


def parse_defaults(text: str) -> dict[str, str]:
    """`model_keys status`'s `default:<role> <engine>` lines: each job's default as the Conduit
    holds it (the models file's, once *Admin › Models* has changed anything)."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        head, _, engine = line.strip().partition(" ")
        if head.startswith("default:") and engine:
            found[head.removeprefix("default:")] = engine
    return found


def parse_status(text: str) -> dict[str, str]:
    """`model_keys status`'s lines (`<name> set|none|lost`), by engine."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        name, _, state = line.strip().partition(" ")
        if name and state in _STATE_WORDS:
            found[name] = state
    return found


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


def _contract(provider: Mapping[str, Any]) -> str:
    """ADR-136 decision 1: "yes" (with the agreement's reference, words only) or "no"."""
    if provider.get("privacy_contract") is not True:
        return "no"
    reference = provider.get("contract_reference")
    return f"yes ({reference})" if reference else "yes"


def list_engines(
    models: Mapping[str, Any],
    env_file: Path,
    states: Mapping[str, str] | None = None,
    defaults: Mapping[str, str] | None = None,
) -> list[str]:
    """What `ospreyflow models` says: each engine, whether each key is present (yes, no, or lost
    after a restore — never the key), whether it is under a privacy contract (ADR-136), and each
    role's default. `states` is the Conduit's answer (ADR-135 Amendment 2); without it, before the
    keys have moved into the gateway, presence is read from `deployment.env`."""
    held = _held(env_file)
    lines = ["Engines:", f"  {LOCAL}: this deployment's own models (no key)"]
    for provider in _providers(models):
        name = str(provider.get("name"))
        if states is not None and name not in states:
            continue  # removed in Admin › Models: the Conduit's list is the deployment's
        if states is not None:
            present = _STATE_WORDS[states[name]]
        else:
            present = "yes" if held.get(key_variable(models, name)) else "no"
        roles = ", ".join(f"{r} {m}" for r, m in (provider.get("roles") or {}).items())
        lines.append(
            f"  {name} ({_label(provider)}): key present: {present}; "
            f"privacy contract: {_contract(provider)} — {roles}"
        )
    named = {str(p.get("name")) for p in _providers(models)}
    for name, state in sorted((states or {}).items()):
        if name not in named:
            lines.append(f"  {name}: added in Admin › Models; key present: {_STATE_WORDS[state]}")
    defaults = dict(defaults) if defaults is not None else _defaults(models)
    lines.append("Defaults:")
    lines += [f"  {role}: {defaults.get(role, LOCAL)}" for role in ROLES]
    if not _providers(models):
        lines.append("No provider is enabled: every role runs on this deployment's own models.")
    return lines


def read_wanted(product: Path) -> dict[str, Any]:
    """The product's own `osprey.yaml`, as the admin has edited it, which may be ahead of what is
    rendered (ADR-137)."""
    candidate = product / "osprey.yaml"
    if candidate.is_file():
        loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            return _models(loaded)
    return {}


def _provider(
    models: Mapping[str, Any], name: str, wanted: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    for provider in _providers(models):
        if provider.get("name") == name:
            return provider
    if any(p.get("name") == name for p in _providers(wanted or {})):
        # ADR-137: enabled in osprey.yaml, not yet rendered. `install` must not be run over a
        # running deployment; `apply` renders it and takes its key.
        raise CommandRefused(
            f"{name} is enabled in osprey.yaml but not yet applied to this deployment. Run "
            "ospreyflow apply: it renders the change, keeps every other setting and secret, and "
            f"takes the key from OSPREY_MODEL_KEY_{name.upper()} or asks for it."
        )
    enabled = ", ".join(str(p.get("name")) for p in _providers(models)) or "none"
    raise CommandRefused(
        f"{name} is not a provider this deployment enables (enabled: {enabled}). Enable it under "
        "models.providers in osprey.yaml and run ospreyflow apply; the local engine has no key."
    )


def read_key(
    models: Mapping[str, Any],
    name: str,
    environ: Mapping[str, str],
    ask_secret: Callable[[str], str],
    wanted: Mapping[str, Any] | None = None,
    known: set[str] | None = None,
) -> tuple[str, str]:
    """The provider's label and the key, from `OSPREY_MODEL_KEY_<NAME>` in the terminal (or the
    single provider's `OSPREY_MODEL_PROVIDER_KEY`), else a hidden prompt. Writes nothing."""
    label = _label_of(models, name, wanted, known)
    variable = key_variable(models, name)
    terminal = f"OSPREY_MODEL_KEY_{name.upper()}"
    key = (environ.get(terminal) or environ.get(variable) or "").strip()
    if not key:
        key = ask_secret(f"Key for {label} ({terminal}; not shown): ").strip()
    if not key:
        raise CommandRefused(f"No key was given for {label}; nothing was changed.")
    if any(ch.isspace() for ch in key):
        raise CommandRefused("A key has no spaces or line breaks in it; nothing was changed.")
    return label, key


def _label_of(
    models: Mapping[str, Any],
    name: str,
    wanted: Mapping[str, Any] | None,
    known: set[str] | None,
) -> str:
    """The engine's label, from `osprey.yaml`, or its name for one added in *Admin › Models*
    (`known`, the Conduit's list); any other name is refused in words."""
    if known and name in known and all(p.get("name") != name for p in _providers(models)):
        return name
    return _label(_provider(models, name, wanted))


def checked_name(
    models: Mapping[str, Any],
    name: str,
    wanted: Mapping[str, Any] | None = None,
    known: set[str] | None = None,
) -> str:
    """The engine's label, or a refusal in words for a name this deployment does not enable."""
    return _label_of(models, name, wanted, known)
