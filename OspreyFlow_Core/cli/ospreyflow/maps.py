"""`ospreyflow map` (`06_DECISIONS.md` ADR-147 decision 6): the basemap providers and the local
basemap for headless use, through the Conduit's own *Maps* code inside its container
(`python -m services.api.map_admin`), so the command line, the set-up console and *Admin › Maps*
are one code, with one audit.

    ospreyflow map list                                   # each provider, its tier and state
    ospreyflow map verify                                 # attribution, and a tier-4 CRS check
    ospreyflow map prefetch                               # every prefetch area, now
    ospreyflow map build <region> [--planetiler-jar PATH] # the tier-1 basemap, built in the Conduit

`build --planetiler-jar` first copies the planetiler release jar the owner has into the tiles
folder (`<tiles>/planetiler/planetiler.jar`), where the Conduit's build reads it; the build runs in
the Conduit, which the command says. The tiles folder's writable `built/` door is made and given to
the Conduit before every `up` (`harness.ingest_uploads.prepare`), so Docker never makes it as root. No map key is ever read,
asked for or printed here: a key is set in *Admin › Maps*.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .home import CommandRefused

#: The Conduit's *Maps* code, run inside its container.
MAP_PATH = ("python", "-m", "services.api.map_admin")
#: Where the Conduit's build reads the jar, and writes what it builds (`services/api/map_admin.py`'s
#: `PLANETILER_JAR` and `BUILT_FOLDER`).
PLANETILER_JAR = Path("planetiler") / "planetiler.jar"
BUILT_FOLDER = "built"
DEFAULT_TILES = "/var/lib/osprey/tiles"


def tiles_folder(config_path: Path) -> Path:
    """The host folder the basemap lives in (`components.storage.tiles`), a relative path read from
    the folder `osprey.yaml` is in, as the harness reads it."""
    raw: Mapping[str, Any] = {}
    if config_path.is_file():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    storage = dict(dict(raw.get("components") or {}).get("storage") or {})
    folder = Path(str(storage.get("tiles") or DEFAULT_TILES)).expanduser()
    return folder if folder.is_absolute() else (config_path.parent / folder).resolve()


def place_jar(jar: Path, tiles: Path) -> Path:
    """The planetiler jar into the tiles folder, refused in words where it is not a `.jar` file."""
    if not jar.is_file():
        raise CommandRefused(f"There is no file at {jar}.")
    if jar.suffix.lower() != ".jar":
        raise CommandRefused(
            f"{jar} is not a .jar. --planetiler-jar wants planetiler's release jar (a Java "
            "program), not a map extract."
        )
    target = tiles / PLANETILER_JAR
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(jar, target)
    return target

