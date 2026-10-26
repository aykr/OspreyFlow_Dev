"""Stand-ins for the case brief's two collaborators, shared by `test_case_brief.py` and
`test_case_brief_routes.py`. No test lives here.

`InMemoryBriefs` applies the very transitions `CaseBriefStore` applies, so a cap or a refusal is the
same in both; `Readable` models the resolvers' *refusals* as well as their grants (`CLAUDE.md` rule
15): a pair nobody may read and one that does not exist both answer None, as the real stores do."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from services.api.case_brief import CaseBriefService, StoredBrief

from schemas.domain import Principal

Update = Callable[[StoredBrief], StoredBrief]


class InMemoryBriefs:
    """What `CaseBriefStore` does, minus the database: `update` hands the stored brief (an empty one
    for a case with none) to the change and keeps what it returns. The change is the shared
    transition, so a cap or a refusal is the same here as there."""

    def __init__(self) -> None:
        self.rows: dict[str, StoredBrief] = {}

    async def get(self, investigation_id: str) -> StoredBrief:
        return self.rows.get(investigation_id) or StoredBrief(investigation_id=investigation_id)

    async def update(self, investigation_id: str, change: Update) -> StoredBrief:
        changed = change(await self.get(investigation_id))
        self.rows[investigation_id] = changed
        return changed


class Readable:
    """The resolvers' stand-in: which principal may read which `(kind, id)` in which case, and the
    title each shows. A pair nobody may read, and one that does not exist, both answer None, as the
    real stores answer (a pattern of another owner, a judgement a citation hides)."""

    def __init__(self) -> None:
        self.titles: dict[tuple[str, str], str] = {}
        self.readers: dict[tuple[str, str], set[str]] = {}
        self.asked: list[tuple[str, str, str]] = []

    def allow(self, kind: str, ref: str, title: str, *principals: Principal) -> None:
        self.titles[(kind, ref)] = title
        self.readers[(kind, ref)] = {p.id for p in principals}

    def revoke(self, kind: str, ref: str) -> None:
        self.readers[(kind, ref)] = set()

    def forget(self, kind: str, ref: str) -> None:
        self.titles.pop((kind, ref), None)
        self.readers.pop((kind, ref), None)

    def resolver(self, kind: str) -> Callable[[str, str, Principal], Awaitable[str | None]]:
        async def title(case_id: str, ref_id: str, principal: Principal) -> str | None:
            self.asked.append((kind, case_id, ref_id))
            if principal.id in self.readers.get((kind, ref_id), set()):
                return self.titles[(kind, ref_id)]
            return None

        return title


def make_service(
    readable: Readable | None = None, store: InMemoryBriefs | None = None
) -> tuple[CaseBriefService, InMemoryBriefs, Readable]:
    readable = readable or Readable()
    store = store or InMemoryBriefs()
    ids = iter(f"req-{n}" for n in range(1, 1000))
    clock = iter(
        datetime(2026, 10, 26, 9, 0, tzinfo=UTC) + timedelta(minutes=n) for n in range(999)
    )
    service = CaseBriefService(
        store,
        {k: readable.resolver(k) for k in ("trend", "pattern", "assessment", "view")},
        new_id=lambda: next(ids),
        now=lambda: next(clock),
    )
    return service, store, readable
