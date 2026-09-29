"""Connector profiles as files — `09_INGEST_STUDIO.md` §2, built in round 13bf.

**What §2 has always said, and what the code did instead.** §2: "Connectors are **profiles**,
following the same pattern as map providers (ADR-016): a validated YAML file in `connectors/`, so
adding a new carrier's CDR layout is a file rather than a release." There was no `connectors/`
directory. Availability was a boolean literal on a catalogue entry
(`ConnectorCatalogueEntry.available`) plus a second, independent literal in
`services/api/studio_profile.py` (`_AVAILABLE_CONNECTORS = frozenset({"generic-csv"})`) — two
hand-maintained truths about the same fact, in different files, with nothing keeping them
together.

The cost of that was measured, not theorised: round 13bc found that B1–B3 could not be walked
through the analyst's own door at all, because the layout the acceptance fixture needs
(`cdr-generic-csv`, with `date_order: dmy`) was declared in the catalogue and refused by the
Studio, and *adding a carrier layout meant editing Python in two places* — exactly the release
§2's own sentence exists to avoid.

**Availability is now derived.** A connector is available iff a profile file exists for it *and*
names a reader this codebase actually implements. Nothing declares availability; it is a
consequence of a file being present, which is what makes "a file rather than a release" true
rather than aspirational. `generic-csv` goes through the same mechanism as every other profile —
one path, not a special case beside it.

**What a profile deliberately does not carry.** No timezone: the source timezone rides on the
binding's own `datetime(tz=...)` transform (`tests/scenarios/fixtures/cdr_recipe.yaml`), and
`packages/knowledge_adapters/datetime_adapter.py` already refuses a value with neither an offset
nor a configured `tz` by name — which is `08_ACCEPTANCE_SCENARIOS.md` B3's own requirement,
already satisfied where it lives. Adding a second place to declare a timezone would create the
same two-truths problem this module exists to remove.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

#: Readers this codebase actually implements. A profile naming anything else parses fine and is
#: reported **unavailable** rather than rejected — a catalogue whose unbuilt entries vanish hides
#: the gap, and `09_INGEST_STUDIO.md` §2's own catalogue exists to show it.
IMPLEMENTED_READERS: frozenset[str] = frozenset({"csv"})


class ConnectorProfile(BaseModel):
    """One `connectors/<id>.yaml`. The connector-level half of a recipe's own source description:
    `RecipeConnector` carries the same fields per recipe, and a recipe may override any of them —
    the profile is the default for a layout, not a lock on it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    group: str
    structured: bool = True
    reader: str = Field(description="Which reader parses this source; `csv` is implemented today")
    delimiter: str = ","
    encoding: str = "utf-8"
    header_rows: int = 1
    #: `01_DOMAIN_MODEL.md` §7 / ADR-017: an ambiguous date order (`03/04/2026`) has no safe
    #: default with both the UK and the US in scope, so a layout that needs one declares it here
    #: once rather than every recipe repeating it.
    date_order: Literal["dmy", "mdy"] | None = None
    source_crs: str | None = None

    @property
    def available(self) -> bool:
        return self.reader in IMPLEMENTED_READERS


def load_connector_profiles(directory: Path) -> dict[str, ConnectorProfile]:
    """Every `*.yaml` in `directory`, keyed by id.

    A file whose `id` disagrees with its own filename is a `ValueError`, not a silent
    mismatch — `connectors/cdr-generic-csv.yaml` declaring `id: something-else` would make the
    Studio offer an id no file answers to, and the failure would surface much later as
    `connector_not_available` on a profile that visibly exists.
    """
    profiles: dict[str, ConnectorProfile] = {}
    if not directory.is_dir():
        return profiles
    for path in sorted(directory.glob("*.yaml")):
        profile = ConnectorProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if profile.id != path.stem:
            raise ValueError(
                f"{path} declares id {profile.id!r} but is named {path.stem!r} — the Studio "
                "resolves a profile by id, so the two must agree"
            )
        profiles[profile.id] = profile
    return profiles


__all__ = ["IMPLEMENTED_READERS", "ConnectorProfile", "load_connector_profiles"]
