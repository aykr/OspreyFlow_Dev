"""Loads a screening list into the deployment (`06_DECISIONS.md` ADR-109 phase F) — replacing a
list of the same name whole. Run as `python -m scripts.load_screening_list <file.yaml>`.

**Rule 9, enforced here, not trusted to the caller.** A list marked `synthetic: true` loads. Any
other list must name its `dataset` (e.g. `opensanctions`) and that dataset must be in the owner's
local `config/real_data_exceptions.yaml` for the `--use` given (`scripts.real_data_exceptions.
is_permitted`) — otherwise nothing is loaded and the script says why. OpenSanctions is CC-BY-NC 4.0
(spec 00 §7): non-commercial use only.

The file's shape: `list_name`, `synthetic`, optionally `dataset`, and `entries`, each with `id`,
`listing` (sanction, pep or adverse_media), `entity_type` (Person or Organisation), `name`, and
optionally `date_of_birth` (ISO) and `country`. Converting a real list's own export to this shape is
the owner's local step; no converter for any real list is committed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from scripts.real_data_exceptions import APPROVED_USES, is_permitted
from services.api.config import PostgresConfig
from services.api.screening import ScreeningEntry, ScreeningListStore

_LISTINGS = {"sanction", "pep", "adverse_media"}
_TYPES = {"Person", "Organisation"}


class ListRefused(Exception):
    """The list may not be loaded, in words."""


def parse_list(raw: dict[str, Any], *, use: str, config_path: Path | None = None) -> tuple[str, list[ScreeningEntry]]:
    synthetic = raw.get("synthetic") is True
    if not synthetic:
        dataset = str(raw.get("dataset") or "").strip()
        if not dataset:
            raise ListRefused("a list not marked synthetic must name its `dataset`")
        permitted = (
            is_permitted(dataset, use)
            if config_path is None
            else is_permitted(dataset, use, config_path=config_path)
        )
        if not permitted:
            raise ListRefused(
                f"{dataset!r} is real data and is not in this device's real_data_exceptions.yaml "
                f"for {use!r} (rule 9); nothing was loaded"
            )
    list_name = str(raw.get("list_name") or "").strip()
    if not list_name:
        raise ListRefused("the list has no `list_name`")
    entries: list[ScreeningEntry] = []
    for item in raw.get("entries") or []:
        if item.get("listing") not in _LISTINGS or item.get("entity_type") not in _TYPES:
            raise ListRefused(f"entry {item.get('id')!r}: listing or entity_type not recognised")
        dob = item.get("date_of_birth")
        entries.append(
            ScreeningEntry(
                id=f"{list_name}:{item['id']}",
                list_name=list_name,
                listing=item["listing"],
                entity_type=item["entity_type"],
                name=str(item["name"]),
                date_of_birth=date.fromisoformat(str(dob)) if dob else None,
                country=item.get("country"),
                synthetic=synthetic,
            )
        )
    return list_name, entries


async def _load(path: Path, use: str) -> int:
    list_name, entries = parse_list(yaml.safe_load(path.read_text(encoding="utf-8")), use=use)
    store = await ScreeningListStore.connect(PostgresConfig.from_env().dsn)
    try:
        count = await store.replace_list(list_name, entries)
    finally:
        await store.close()
    print(f"Loaded {count} entries into {list_name!r}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.load_screening_list")
    parser.add_argument("path", type=Path)
    parser.add_argument("--use", default="local_development", choices=APPROVED_USES)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return asyncio.run(_load(args.path, args.use))
    except ListRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
