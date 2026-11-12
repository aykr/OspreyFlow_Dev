"""Loads a screening list into the deployment (`06_DECISIONS.md` ADR-109 phase F) — replacing a
list of the same name whole. Run as `python -m scripts.load_screening_list <file.yaml>`.

**Rule 9, enforced here, not trusted to the caller.** A list marked `synthetic: true` loads. Any
other list must name its `dataset` (e.g. `opensanctions`) and that dataset must be in the owner's
local `config/real_data_exceptions.yaml` for the `--use` given (`scripts.real_data_exceptions.
is_permitted`) — otherwise nothing is loaded and the script says why. OpenSanctions is CC-BY-NC 4.0
(spec 00 §7): non-commercial use only. A list whose dataset is `opensanctions` or `un_consolidated`
is refused even then: their licences are not confirmed (the owner's answer of 1 November 2026).

The file's shape: `list_name`, `synthetic`, optionally `dataset`, optionally `marking` (the
list's `classification` and `handling_code`, from the deployment's handling scheme; left out,
OFFICIAL and P: ADR-146 Amendment 7, a match on the list shown only to a reader it clears), and
`entries`, each with `id`, `listing` (sanction, pep or adverse_media), `entity_type` (Person or
Organisation), `name`, and optionally `date_of_birth` (ISO) and `country`. Converting a real list's
own export to this shape is the owner's local step; no converter for any real list is committed.
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
from services.api.screening import MarkingLowered, ScreeningEntry, ScreeningListStore
from services.api.screening_refresh import LICENCE_NOT_CONFIRMED
from services.ingest.ceiling import DeploymentCeiling

from ontology.handling import HandlingScheme, load_uk_le_scheme

_LISTINGS = {"sanction", "pep", "adverse_media"}
_TYPES = {"Person", "Organisation"}


class ListRefused(Exception):
    """The list may not be loaded, in words."""


def _marking(
    raw: dict[str, Any], scheme: HandlingScheme, ceiling: DeploymentCeiling | None = None
) -> tuple[str | None, str | None]:
    """The list's `marking` (ADR-146 Amendment 7): a classification and a handling code the
    scheme defines, refused in words otherwise; left out, `(None, None)`, OFFICIAL and P. Refused
    too, after the lane review (item 11): a classification above the deployment's ceiling
    (`OSPREY_HIGHEST_MARKING`, ADR-148), which it may not hold, and a handling code restricted to a
    unit, since a list's match is written in the deployer's unit and the code would name the wrong
    one."""
    marking = raw.get("marking")
    if marking is None:
        return None, None
    if not isinstance(marking, dict) or set(marking) != {"classification", "handling_code"}:
        raise ListRefused("`marking` names exactly a `classification` and a `handling_code`")
    classification, code = str(marking["classification"]), str(marking["handling_code"])
    if classification not in scheme.classification:
        raise ListRefused(f"`marking`: {classification!r} is not a classification of this scheme")
    if code not in scheme.handling_codes:
        raise ListRefused(f"`marking`: {code!r} is not a handling code of this scheme")
    if scheme.handling_codes[code].dissemination == "restricted":
        raise ListRefused(
            f"`marking`: {code!r} restricts a list to one unit, which a list's matches cannot "
            "name; use a handling code every unit may receive"
        )
    if (ceiling or DeploymentCeiling.from_env(scheme)).above(classification):
        raise ListRefused(
            f"`marking`: {classification!r} is above this deployment's highest marking; nothing "
            "was loaded"
        )
    return classification, code


def parse_list(
    raw: dict[str, Any],
    *,
    use: str,
    config_path: Path | None = None,
    scheme: HandlingScheme | None = None,
    ceiling: DeploymentCeiling | None = None,
) -> tuple[str, list[ScreeningEntry]]:
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
        # The owner's answer of 1 November 2026: UN and OpenSanctions are synthetic-only until
        # their licences are confirmed, here as in a subscription's refresh (`screening_refresh`).
        unconfirmed = LICENCE_NOT_CONFIRMED.get(dataset.lower())
        if unconfirmed is not None:
            raise ListRefused(
                f"{dataset!r}: this list's licence is not confirmed: {unconfirmed}. Until it is, "
                "only a synthetic list may be loaded; nothing was loaded"
            )
    list_name = str(raw.get("list_name") or "").strip()
    if not list_name:
        raise ListRefused("the list has no `list_name`")
    classification, handling_code = _marking(raw, scheme or load_uk_le_scheme(), ceiling)
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
                classification=classification,
                handling_code=handling_code,
            )
        )
    return list_name, entries


async def _load(path: Path, use: str) -> int:
    list_name, entries = parse_list(yaml.safe_load(path.read_text(encoding="utf-8")), use=use)
    store = await ScreeningListStore.connect(PostgresConfig.from_env().dsn)
    try:
        # The orchestrator's review, item 8: a reload never lowers the list's kept marking.
        count = await store.replace_list(list_name, entries, scheme=load_uk_le_scheme())
    except MarkingLowered as lowered:
        raise ListRefused(str(lowered)) from lowered
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
