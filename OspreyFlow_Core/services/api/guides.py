"""The guides, read from Home by the places a person may open (`06_DECISIONS.md` ADR-145
Amendment 10; ADR-145 decision 1 and N6; ADR-115 E3).

`GET /v1/guides/{guide}` answers the deployment's own PDF of a guide (`docs/pdf/`, the version the
image was built with) only to a principal whose rights open the place the guide belongs to: the user
guide with the Glass, the developer guide with the Ingest Studio, the administration guide with
Admin. The architecture guide is not served. Home links a guide only under a card the person's
rights already open, but that is a convenience, never the gate (rule 3): this check is the gate, and
it is the same test the place switcher makes (`apps/workspace/src/shell/places.ts`'s `placesFor`):
one of the place's rights, and every right it `needs`.

The places' rights are written here, not read from `places.json`, because the Conduit's image does
not carry the workspace; `tests/services/api/test_guides.py` holds this table to `places.json`, so
the two cannot drift apart unseen.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from schemas.rights import Right, rights_for


@dataclass(frozen=True)
class Guide:
    """A guide Home links, the place whose card it sits under, and its file in `docs/pdf/`."""

    id: str
    place: str
    place_name: str
    title: str
    source: str  # the Markdown file, the key `docs/pdf/manifest.json` records it under

    @property
    def pdf(self) -> str:
        return self.source.removesuffix(".md") + ".pdf"


GUIDES: dict[str, Guide] = {
    "user": Guide("user", "glass", "the Glass", "user guide", "user-guide.md"),
    "developer": Guide("developer", "ingest", "the Ingest Studio", "developer guide",
                       "developer-guide.md"),
    "administration": Guide("administration", "admin", "Admin", "administration guide",
                            "administration-guide.md"),
}  # fmt: skip

#: The rights that open each place a guide belongs to, any one of them (`places.json`'s `rights`).
PLACE_RIGHTS: dict[str, frozenset[Right]] = {
    "glass": frozenset({
        Right.ASK_MODEL, Right.CONFIRM_INFERRED, Right.CREATE_CASE, Right.EDIT_GRAPH, Right.EXPORT,
        Right.EXTRACT_FILES, Right.INVESTIGATE, Right.MANAGE_STRENGTH_INFLUENCERS,
        Right.PROPOSE_TYPES, Right.READ_ALERT_QUEUE, Right.READ_DATA_FEEDS, Right.READ_REPORT_FEED,
        Right.READ_REPORTS, Right.RECORD_ASSESSMENT, Right.REMOVE_CASE, Right.RESOLVE_ENTITIES,
        Right.RUN_ANALYSIS, Right.SHARE_CASE, Right.TRACE_OWNERSHIP,
    }),
    "ingest": frozenset({Right.EDIT_PIPELINES}),
    "admin": frozenset({
        Right.ADMINISTER_SYSTEM, Right.MANAGE_DASHBOARDS, Right.MANAGE_PEOPLE,
        Right.OPERATE_SCHEDULES, Right.READ_AUDIT,
    }),
}  # fmt: skip
#: What each of those places needs as well (`places.json`'s `needs`): none of the three needs any.
PLACE_NEEDS: dict[str, frozenset[Right]] = {"glass": frozenset(), "ingest": frozenset(),
                                            "admin": frozenset()}  # fmt: skip

#: Where the PDFs are: `/app/docs/pdf` in the Conduit's image (its Dockerfile copies them there),
#: the checkout's `docs/pdf` in development. `OSPREY_GUIDES_DIR` overrides it, for a test.
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "docs" / "pdf"


def guides_dir() -> Path:
    return Path(os.environ.get("OSPREY_GUIDES_DIR") or _DEFAULT_DIR)


def opens_place(place: str, roles: Iterable[str]) -> bool:
    """Whether a principal with these token roles is offered the place: one of its rights and every
    right it needs, as the switcher and Home decide."""
    held = rights_for(roles)
    return bool(held & PLACE_RIGHTS[place]) and PLACE_NEEDS[place] <= held


def unknown(guide: str) -> dict[str, object]:
    return {
        "error": "no_such_guide",
        "guides": sorted(GUIDES),
        "message": f"There is no guide called “{guide}”. The guides are the user guide, the "
        "developer guide and the administration guide.",
    }


def refusal(guide: Guide) -> dict[str, object]:
    """The 403, in words: the place the guide opens with, and the rights any one of which opens
    it."""
    return {
        "error": "place_required",
        "place": guide.place,
        "rights": sorted(r.value for r in PLACE_RIGHTS[guide.place]),
        "message": f"The {guide.title} opens with {guide.place_name}, which your roles do not "
        f"open. Ask an administrator for a role that opens {guide.place_name}.",
    }


def not_carried(guide: Guide) -> dict[str, object]:
    return {
        "error": "guide_not_carried",
        "message": f"This deployment was built without the {guide.title}'s PDF, so it cannot be "
        "read here. Ask an administrator to rebuild the deployment.",
    }


def version(guide: Guide, folder: Path) -> str | None:
    """The guide's version as `docs/pdf/manifest.json` records it, or none if it is unreadable."""
    try:
        entry = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))[guide.source]
        return str(entry["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
