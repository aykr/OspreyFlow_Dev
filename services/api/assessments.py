"""Assessment objects — `01_DOMAIN_MODEL.md` §5, `06_DECISIONS.md` ADR-046 (accepted), Phase 8
Stage 4b. `Judgement`/`IntelligenceGap`/`Assumption` persistence, investigation-scoped
control-plane metadata, the same "small, relational, not graph content" shape `sites.py`/
`investigations.py`/`pattern_store.py` already are — Postgres, idempotent bootstrap SQL, no
migration framework.

**Backend only.** No Glass surface here (Stage 4c, `02_GLASS_FRONTEND.md` §9) and no export-gate
change (Stage 4d/4e) — ADR-046's own export requirement (an exported judgement's `supporting`
citations independently checked against the *exporting analyst's* own access) belongs to Stage 4d,
named here so a future reader does not go looking for it in this module.

**`owning_unit`-scoped like `sites.py`, not owner-only like `pattern_store.py`.** A judgement
belongs to an investigation multiple analysts in the same unit can read and write — the same
`principal.org_unit == investigation.owning_unit` authorization boundary
`services/api/investigations.py`'s own module docstring establishes, not a single-owner object.
`get_authorized`/`list_authorized` below filter `owning_unit` in the query itself
(`scripts/authorized_query_check.py`), the *ownership* half of access; `06_DECISIONS.md` ADR-046's
own per-citation hide rule is a second, independent check below that, exactly the two-check
composition `alerts.py`'s own `get_authorized`/`evidence_available` split already establishes.

**ADR-046's access rule, and its one disclosed limitation.** "A judgement is hidden from a viewer,
in full, when that viewer's access does not cover at least one of its own `supporting`
references" — `_all_visible` below is the one function both `list_visible_judgements` (the
hide-in-full filter) and the citation checks read. **Only a `NodeId` citation can be positively
confirmed visible today** — `GraphPort` has no `get_edge`, and no document store exists yet
(`07_BUILD_PLAN.md`'s own "Stage 4b known gaps" entry). An `EdgeId`/`DocumentId` citation
(`Judgement.supporting`/`contradicting`'s own docstring in `schemas/domain.py`) therefore always
reads as unreadable — the same fail-closed default this codebase already applies wherever it
cannot positively confirm access, not a new posture invented here. A judgement whose *only*
supporting evidence is an edge or a document is consequently hidden from every viewer, including
its own author, until that gap closes — disclosed, not silently accepted.

**The review-flag loop.** `flag_judgements_citing_superseded_node` is the function
`services/extract/writer.py`'s `confirm_node`/`retract_node` and `services/api/supersede.py`'s
`submit_supersede_node`/`run_supersede_node_job` each call, optionally, immediately after a real
`supersede_node` succeeds — `01_DOMAIN_MODEL.md` §5's own literal text ("When a supporting node is
later split, corrected or retracted, every judgement resting on it is flagged for review") names
`supporting` only; a `contradicting` citation's own content change is **not** flagged by this
function — a narrower, disclosed scope decision, not an oversight (`07_BUILD_PLAN.md`'s own gaps
entry has the reasoning). An unreadable (not content-changed) `contradicting` reference is a
*different* trigger, flagged lazily the first time a read discovers it
(`_flag_unreadable_contradicting_lazily` below) — there is no proactive, scheduled scan for this in
Stage 4b, the same "re-flags only on process restart"-class timing gap Phase 5a's own reverse-index
disclosure already accepted for a different feature, disclosed here for this one."""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
from pydantic import BaseModel

from ports.graph import GraphPort
from schemas.domain import Assumption, IntelligenceGap, Judgement, Principal

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS judgements (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    statement TEXT NOT NULL,
    probability_band TEXT NOT NULL,
    supporting TEXT[] NOT NULL,
    contradicting TEXT[] NOT NULL,
    author TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    flagged_for_review BOOLEAN NOT NULL DEFAULT FALSE,
    flag_reason TEXT
);
CREATE INDEX IF NOT EXISTS judgements_investigation_id_idx ON judgements (investigation_id);
CREATE INDEX IF NOT EXISTS judgements_owning_unit_idx ON judgements (owning_unit);

CREATE TABLE IF NOT EXISTS intelligence_gaps (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    question TEXT NOT NULL,
    raised_by TEXT NOT NULL,
    linked_entities TEXT[] NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS intelligence_gaps_investigation_id_idx
    ON intelligence_gaps (investigation_id);

CREATE TABLE IF NOT EXISTS assumptions (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    statement TEXT NOT NULL,
    if_false_impact TEXT NOT NULL,
    linked_judgements TEXT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS assumptions_investigation_id_idx ON assumptions (investigation_id);
"""


class NoSupportingReferenceError(Exception):
    """`01_DOMAIN_MODEL.md` §5: "a judgement cannot be saved without at least one supporting
    reference" — A13's own literal assertion."""


class JudgementNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the judgement exists but `owning_unit` does
    not match the calling principal's own `org_unit`: the same existence-leak discipline
    `SiteNotFoundError`/`InvestigationNotFoundError` already establish."""


class GapNotFoundError(Exception):
    """Same existence-leak discipline as `JudgementNotFoundError`."""


class AssumptionNotFoundError(Exception):
    """Same existence-leak discipline as `JudgementNotFoundError`."""


def _row_to_judgement(row: asyncpg.Record) -> Judgement:
    return Judgement(
        id=row["id"],
        investigation_id=row["investigation_id"],
        statement=row["statement"],
        probability_band=row["probability_band"],
        supporting=list(row["supporting"]),
        contradicting=list(row["contradicting"]),
        author=row["author"],
        created_at=row["created_at"],
        flagged_for_review=row["flagged_for_review"],
        flag_reason=row["flag_reason"],
    )


def _row_to_gap(row: asyncpg.Record) -> IntelligenceGap:
    return IntelligenceGap(
        id=row["id"],
        investigation_id=row["investigation_id"],
        question=row["question"],
        raised_by=row["raised_by"],
        linked_entities=list(row["linked_entities"]),
        status=row["status"],
        created_at=row["created_at"],
    )


def _row_to_assumption(row: asyncpg.Record) -> Assumption:
    return Assumption(
        id=row["id"],
        investigation_id=row["investigation_id"],
        statement=row["statement"],
        if_false_impact=row["if_false_impact"],
        linked_judgements=list(row["linked_judgements"]),
        created_at=row["created_at"],
    )


class JudgementStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> JudgementStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def save(self, judgement: Judgement, principal: Principal) -> Judgement:
        """`01_DOMAIN_MODEL.md` §5's own evidence-link constraint, enforced here — the one place
        every route saving a judgement must go through — not left to a model-level validator that
        cannot distinguish a legitimate in-progress edit from a genuinely empty save."""
        if not judgement.supporting:
            raise NoSupportingReferenceError(judgement.id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO judgements (id, investigation_id, owning_unit, statement, "
                "probability_band, supporting, contradicting, author, created_at, "
                "flagged_for_review, flag_reason) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) "
                "ON CONFLICT (id) DO UPDATE SET statement = EXCLUDED.statement, "
                "probability_band = EXCLUDED.probability_band, "
                "supporting = EXCLUDED.supporting, contradicting = EXCLUDED.contradicting",
                judgement.id,
                judgement.investigation_id,
                principal.org_unit,
                judgement.statement,
                judgement.probability_band,
                judgement.supporting,
                judgement.contradicting,
                judgement.author,
                judgement.created_at,
                judgement.flagged_for_review,
                judgement.flag_reason,
            )
        return judgement

    async def get(self, judgement_id: str) -> Judgement:
        """No authorization check here — the raw record lookup, `get_authorized`'s own base, the
        same `sites.py::SiteStore.get` shape."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM judgements WHERE id = $1", judgement_id)
        if row is None:
            raise JudgementNotFoundError(judgement_id)
        return _row_to_judgement(row)

    async def get_authorized(self, judgement_id: str, principal: Principal) -> Judgement:
        """`owning_unit` filtered in the query itself — `scripts/authorized_query_check.py`'s own
        shape, `sites.py::get_authorized`'s twin. This is the *ownership* check only; ADR-046's
        own per-citation hide rule is a separate, second check (`judgement_visible_to` below)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM judgements WHERE id = $1 AND owning_unit = $2",
                judgement_id,
                principal.org_unit,
            )
        if row is None:
            raise JudgementNotFoundError(judgement_id)
        return _row_to_judgement(row)

    async def list_for_investigation(
        self, investigation_id: str, principal: Principal
    ) -> list[Judgement]:
        """`owning_unit`-scoped, the same ownership half `get_authorized` checks — ADR-046's own
        per-citation hide rule is layered on top by `list_visible_judgements`, not here."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM judgements WHERE investigation_id = $1 AND owning_unit = $2 "
                "ORDER BY created_at",
                investigation_id,
                principal.org_unit,
            )
        return [_row_to_judgement(row) for row in rows]

    async def list_citing(self, referent_id: str) -> list[Judgement]:
        """Every judgement, across every investigation and unit, whose `supporting` or
        `contradicting` list names `referent_id` — the review-flag loop's own lookup
        (`flag_judgements_citing_superseded_node`). Deliberately unscoped by `owning_unit`: a
        judgement citing a node that is being corrected must be found and flagged regardless of
        which unit owns the judgement, the same "the evaluator's own unscoped read" shape
        `06_DECISIONS.md` ADR-038's own addendum already establishes for a different mechanism —
        finding a row and disclosing it to a principal are different steps, and this function only
        ever finds and flags, never returns judgement content to an unauthorised reader."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM judgements WHERE $1 = ANY(supporting) OR $1 = ANY(contradicting)",
                referent_id,
            )
        return [_row_to_judgement(row) for row in rows]

    async def flag_for_review(self, judgement_id: str, *, reason: str) -> None:
        """Idempotent — flagging an already-flagged judgement a second time (a different citation
        superseded, or a second unreadable `contradicting` discovered) leaves the original
        `flag_reason` in place rather than overwriting it, so the first reason a reviewer would
        need to see is not silently lost under a second one."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE judgements SET flagged_for_review = TRUE, "
                "flag_reason = COALESCE(flag_reason, $2) WHERE id = $1",
                judgement_id,
                reason,
            )


class IntelligenceGapStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> IntelligenceGapStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def save(self, gap: IntelligenceGap, principal: Principal) -> IntelligenceGap:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO intelligence_gaps (id, investigation_id, owning_unit, question, "
                "raised_by, linked_entities, status, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                "ON CONFLICT (id) DO UPDATE SET question = EXCLUDED.question, "
                "linked_entities = EXCLUDED.linked_entities, status = EXCLUDED.status",
                gap.id,
                gap.investigation_id,
                principal.org_unit,
                gap.question,
                gap.raised_by,
                gap.linked_entities,
                gap.status,
                gap.created_at,
            )
        return gap

    async def get_authorized(self, gap_id: str, principal: Principal) -> IntelligenceGap:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM intelligence_gaps WHERE id = $1 AND owning_unit = $2",
                gap_id,
                principal.org_unit,
            )
        if row is None:
            raise GapNotFoundError(gap_id)
        return _row_to_gap(row)

    async def list_for_investigation(
        self, investigation_id: str, principal: Principal
    ) -> list[IntelligenceGap]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM intelligence_gaps WHERE investigation_id = $1 AND owning_unit = $2 "
                "ORDER BY created_at",
                investigation_id,
                principal.org_unit,
            )
        return [_row_to_gap(row) for row in rows]


class AssumptionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> AssumptionStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def save(self, assumption: Assumption, principal: Principal) -> Assumption:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO assumptions (id, investigation_id, owning_unit, statement, "
                "if_false_impact, linked_judgements, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "ON CONFLICT (id) DO UPDATE SET statement = EXCLUDED.statement, "
                "if_false_impact = EXCLUDED.if_false_impact, "
                "linked_judgements = EXCLUDED.linked_judgements",
                assumption.id,
                assumption.investigation_id,
                principal.org_unit,
                assumption.statement,
                assumption.if_false_impact,
                assumption.linked_judgements,
                assumption.created_at,
            )
        return assumption

    async def get_authorized(self, assumption_id: str, principal: Principal) -> Assumption:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM assumptions WHERE id = $1 AND owning_unit = $2",
                assumption_id,
                principal.org_unit,
            )
        if row is None:
            raise AssumptionNotFoundError(assumption_id)
        return _row_to_assumption(row)

    async def list_for_investigation(
        self, investigation_id: str, principal: Principal
    ) -> list[Assumption]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM assumptions WHERE investigation_id = $1 AND owning_unit = $2 "
                "ORDER BY created_at",
                investigation_id,
                principal.org_unit,
            )
        return [_row_to_assumption(row) for row in rows]


async def _all_visible(graph: GraphPort, principal: Principal, ref_ids: list[str]) -> bool:
    """`06_DECISIONS.md` ADR-046's own per-citation check, the same `alerts.py::evidence_available`
    shape — every id must resolve to a real, visible node for the whole list to count as visible.
    An empty list is vacuously visible (nothing to hide behind); callers of this function for
    `supporting` never pass one, since `JudgementStore.save` already refuses to store a judgement
    with no supporting references."""
    for ref_id in ref_ids:
        if await graph.get_node(ref_id, principal) is None:
            return False
    return True


async def judgement_visible_to(
    judgement: Judgement, principal: Principal, graph: GraphPort
) -> bool:
    """`06_DECISIONS.md` ADR-046: "A judgement is hidden from a viewer, in full, when that
    viewer's access does not cover at least one of its own `supporting` references." Only
    `supporting` gates visibility — an unreadable `contradicting` reference never hides the
    judgement (the companion behaviour `_flag_unreadable_contradicting_lazily` records instead)."""
    return await _all_visible(graph, principal, judgement.supporting)


async def _flag_unreadable_contradicting_lazily(
    judgement: Judgement, principal: Principal, graph: GraphPort, store: JudgementStore
) -> None:
    """Read-triggered, not proactively scanned — the disclosed timing gap this module's own
    docstring names. Only ever flags; never un-flags, and never blocks the read that triggered
    it — the judgement itself still renders to `principal` (it is `contradicting`, not
    `supporting`, that is unreadable)."""
    if judgement.flagged_for_review:
        return
    if not await _all_visible(graph, principal, judgement.contradicting):
        await store.flag_for_review(
            judgement.id, reason="an unreadable contradicting reference was found at read time"
        )


async def list_visible_judgements(
    store: JudgementStore, investigation_id: str, principal: Principal, graph: GraphPort
) -> list[Judgement]:
    """The one function a route should call to render the Judgements tab (§9,
    `02_GLASS_FRONTEND.md`) — composes the ownership check (`list_for_investigation`), ADR-046's
    own hide-in-full filter, and the lazy `contradicting`-unreadable flag in one pass."""
    candidates = await store.list_for_investigation(investigation_id, principal)
    visible: list[Judgement] = []
    for judgement in candidates:
        if not await judgement_visible_to(judgement, principal, graph):
            continue
        await _flag_unreadable_contradicting_lazily(judgement, principal, graph, store)
        visible.append(judgement)
    return visible


async def flag_judgements_citing_superseded_node(
    store: JudgementStore, node_id: str
) -> list[str]:
    """The review-flag loop's own hook — `01_DOMAIN_MODEL.md` §5: "When a supporting node is later
    split, corrected or retracted, every judgement resting on it is flagged for review." Called
    immediately after a real `GraphPort.supersede_node` succeeds
    (`services/extract/writer.py::confirm_node`/`retract_node`,
    `services/api/supersede.py::submit_supersede_node`/`run_supersede_node_job`, each optionally,
    via a `judgement_store` parameter that defaults to `None` so every existing caller and test of
    those four functions is unaffected). Matches `supporting` only, per the spec's own literal
    text — a `contradicting` citation's own content change is not flagged here, a narrower,
    disclosed scope decision (`07_BUILD_PLAN.md`'s own Stage 4b known-gaps entry).

    Returns the flagged judgement ids, so a caller (a route, a test) can report exactly what was
    affected rather than trusting the write happened."""
    citing = await store.list_citing(node_id)
    flagged: list[str] = []
    for judgement in citing:
        if node_id not in judgement.supporting:
            continue
        await store.flag_for_review(judgement.id, reason=f"cited node {node_id} was superseded")
        flagged.append(judgement.id)
    return flagged


def new_judgement(
    *,
    investigation_id: str,
    statement: str,
    probability_band: str,
    supporting: list[str],
    contradicting: list[str] | None = None,
    author: str,
) -> Judgement:
    """A thin constructor, not a route — assigns `id`/`created_at` the same way every other
    `new_id()`/`datetime.now(UTC)` call site in this package already does, so a route handler
    builds the model the same way a test fixture does."""
    from conduit_common.identity import new_id

    return Judgement(
        id=new_id(),
        investigation_id=investigation_id,
        statement=statement,
        probability_band=probability_band,
        supporting=supporting,
        contradicting=contradicting or [],
        author=author,
        created_at=datetime.now(UTC),
    )


class SaveJudgementRequest(BaseModel):
    """The wire shape for the eventual Stage 4c route — not routed here (backend-only scope), but
    shaped now so Stage 4c does not need to re-derive it."""

    investigation_id: str
    statement: str
    probability_band: str
    supporting: list[str]
    contradicting: list[str] = []


__all__ = [
    "AssumptionNotFoundError",
    "AssumptionStore",
    "GapNotFoundError",
    "IntelligenceGapStore",
    "JudgementNotFoundError",
    "JudgementStore",
    "NoSupportingReferenceError",
    "SaveJudgementRequest",
    "flag_judgements_citing_superseded_node",
    "judgement_visible_to",
    "list_visible_judgements",
    "new_judgement",
]
