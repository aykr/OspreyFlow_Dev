"""The install answers file, `install.yaml` (`06_DECISIONS.md` ADR-114 Amendment 3 decision 5): what
every question writes — the guided page, the prompts, or a hand-written file passed to
`ospreyflow install --config` — and the `osprey.yaml` it becomes. One file, so a person at the page,
a person at the prompts and CI install the same way.

    mode: lite                     # lite | small | enterprise
    components:
      dashboards: true             # report-sync and Superset (`reporting:`); on by default
    folders:                       # host folders; absolute, or under the home folder with ~
      ingest: ~/OspreyFlow/ingest  # what the Ingest Studio lists (read-only to the Conduit)
      tiles: ~/OspreyFlow/basemap  # where a built basemap lives
    models:
      local_only: true             # no case content leaves the deployment
    demo_packs: [operation-ledger, hmp]
    paysim_file: ~/Downloads/PS_20174392719_1491204439457_log.csv
    cloud:                         # small and enterprise only; used from stages B6 and B7
      provider: aws                # aws | azure
      region: eu-west-2
      domain: osprey.example.org
    config: ./osprey.yaml          # instead of the sections above: use this osprey.yaml as it is

Unknown keys are refused by name, as `osprey.yaml`'s are, so a typo never silently means the
default. This module depends on nothing but PyYAML: the command is small, and the deployment's own
schema checks the result when it is rendered.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ospreyflow.home import LITE_ORIGIN

MODES = ("lite", "small", "enterprise")
CLOUDS = ("aws", "azure")
#: Each mode's `osprey.yaml` profile (`spec/05_DEPLOYMENT.md` §2).
PROFILES = {"lite": "local-lite", "small": "small", "enterprise": "cluster"}

_TOP = {"mode", "components", "folders", "models", "demo_packs", "paysim_file", "cloud", "config"}
_SECTIONS = {
    "components": {"dashboards"},
    "folders": {"ingest", "tiles"},
    "models": {"local_only"},
    "cloud": {"provider", "region", "domain", "size"},
}
#: The sections a named `config:` replaces; giving both is refused rather than one silently winning.
_CONFIG_SECTIONS = ("components", "folders", "models")


class AnswersRefused(Exception):
    """The answers cannot be installed from; the message says which key and why."""


@dataclass(frozen=True)
class Answers:
    mode: str
    dashboards: bool = True
    ingest: Path | None = None
    tiles: Path | None = None
    local_only: bool = True
    demo_packs: tuple[str, ...] = ()
    paysim_file: Path | None = None
    cloud: dict[str, str] = field(default_factory=dict)
    config: Path | None = None


def _known(where: str, raw: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise AnswersRefused(
            f"{where} has no setting called {', '.join(repr(k) for k in unknown)}; "
            f"the settings are {', '.join(sorted(allowed))}"
        )


def _host_path(key: str, value: object, home: Path) -> Path:
    text = str(value)
    if text.startswith("~"):
        return home / text[1:].lstrip("/")
    path = Path(text)
    if not path.is_absolute():
        raise AnswersRefused(f"{key} is a relative path ({text}); give it from / or from ~")
    return path


def _boolean(key: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise AnswersRefused(f"{key} is true or false, not {value!r}")
    return value


def load_answers(
    raw: Mapping[str, Any] | Path, *, packs: Iterable[str], home: Path | None = None
) -> Answers:
    """The answers in `raw` (a mapping, or a path to `install.yaml`), checked. `packs` are the demo
    packs this checkout offers (`scripts/demo_packs.py`); `home` stands in for `~`."""
    home = home or Path.home()
    if isinstance(raw, Path):
        loaded = yaml.safe_load(raw.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise AnswersRefused(f"{raw} does not hold settings")
        raw = loaded
    _known("The answers file", raw, _TOP)
    mode = raw.get("mode")
    if mode not in MODES:
        raise AnswersRefused(f"mode is one of {', '.join(MODES)}, not {mode!r}")
    sections: dict[str, Mapping[str, Any]] = {}
    for name, allowed in _SECTIONS.items():
        section = raw.get(name) or {}
        if not isinstance(section, Mapping):
            raise AnswersRefused(f"{name} holds settings, not {section!r}")
        _known(name, section, allowed)
        sections[name] = section

    config = raw.get("config")
    if config is not None and any(raw.get(name) for name in _CONFIG_SECTIONS):
        raise AnswersRefused(
            "give either config (an osprey.yaml used as it is) or components, folders and models, "
            "not both"
        )

    cloud = {k: str(v) for k, v in sections["cloud"].items()}
    if mode == "lite" and cloud:
        raise AnswersRefused("cloud settings are for the small and enterprise modes, not lite")
    if cloud and cloud.get("provider") not in CLOUDS:
        raise AnswersRefused(
            f"cloud provider is one of {', '.join(CLOUDS)}, not {cloud.get('provider')!r}"
        )

    offered = tuple(packs)
    chosen = tuple(str(p) for p in raw.get("demo_packs") or ())
    for pack in chosen:
        if pack not in offered:
            raise AnswersRefused(
                f"there is no demo pack called {pack!r}; the packs are {', '.join(offered)}"
            )

    if raw.get("paysim_file") and "paysim" not in chosen:
        raise AnswersRefused(
            "paysim_file is the PaySim pack's file, and the paysim pack is not chosen"
        )

    folders = sections["folders"]
    return Answers(
        mode=str(mode),
        dashboards=_boolean(
            "components.dashboards", sections["components"].get("dashboards", True)
        ),
        ingest=_host_path("folders.ingest", folders["ingest"], home)
        if "ingest" in folders
        else home / "OspreyFlow" / "ingest",
        tiles=_host_path("folders.tiles", folders["tiles"], home)
        if "tiles" in folders
        else home / "OspreyFlow" / "basemap",
        local_only=_boolean("models.local_only", sections["models"].get("local_only", True)),
        demo_packs=chosen,
        paysim_file=_host_path("paysim_file", raw["paysim_file"], home)
        if raw.get("paysim_file")
        else None,
        cloud=cloud,
        config=_host_path("config", config, home) if config is not None else None,
    )


def osprey_config(answers: Answers, base: Mapping[str, Any]) -> dict[str, Any]:
    """The `osprey.yaml` the answers make: the product's committed defaults (`base`) with what the
    answers decide written over them — or, when they name a `config`, that file exactly."""
    if answers.config is not None:
        loaded = yaml.safe_load(answers.config.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise AnswersRefused(f"{answers.config} does not hold settings")
        return loaded
    config = copy.deepcopy(dict(base))
    config["profile"] = PROFILES[answers.mode]
    storage = config.setdefault("components", {}).setdefault("storage", {})
    storage["ingest"] = str(answers.ingest)
    storage["tiles"] = str(answers.tiles)
    config.setdefault("models", {})["local_only"] = answers.local_only
    config["reporting"] = {"sync": answers.dashboards, "superset": answers.dashboards}
    # ADR-114 Amendment 4: every address derives from this one. Lite answers on this machine by
    # name; a cloud install at the client's own domain, over HTTPS.
    network = config.setdefault("network", {})
    if answers.mode == "lite":
        network["public_origin"] = LITE_ORIGIN
    elif answers.cloud.get("domain"):
        network["public_origin"] = f"https://{answers.cloud['domain']}"
    return config
