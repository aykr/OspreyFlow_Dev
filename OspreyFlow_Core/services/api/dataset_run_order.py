"""A dataset's run order, stored (slice IS6a; ADR-140 Amendment 22 item 8; ADR-141 Amendment 2
point 6; the owner's rulings of 24 November 2026). **Nothing is run here**: this is the order a
person set on the dataset map, kept with the dataset.

**What the order is stored as: "runs after" links**, `{pipeline: [the pipelines it runs after]}`.
A pipeline with no link runs after nothing. It is a graph, not a list, so that a failure can stop
only what depends on it (ADR-141 Amendment 2 point 2) and so that a cycle (a pipeline that must
run after itself, directly or through others) is possible, and refused.

**The rules, each a function or a store method below, so its test can remove it alone:**

- **Versioned.** Every save is the next number (the first is 1; none stored is 0), kept with who
  saved it and when; an older number stays. A save names the number its person read
  (`expected_version`, required) and is refused, in words and with nothing changed, when the
  order has moved on (`refuse_a_stale_number`), never a silent overwrite. On Postgres the number
  is the key (`dataset_id`, `version`) and the check runs under the dataset's lock, so two saves
  of one number cannot both land.
- **A cycle is refused on save, in words naming the pipelines in it** (`pipelines_in_a_cycle`, by
  Tarjan's strongly connected components: a pipeline is in a cycle when it is in a component of
  two or more, or links to itself). The saver is told the names the Studio shows (the label), and
  no pipeline that only hangs off a cycle.
- **An undeployed pipeline may be in the order**: the Studio shows it "not deployed", and a later
  load says "not run: not deployed".
- **A saver names only the pipelines of this dataset they may see** (`StudioRecipeStore.list_all`,
  which reads as the person: the unit's own, at whatever status, kept to the datasets the person
  reaches), and not a previous version. Another unit's, another dataset's, one placed in none, a
  previous version and one that does not exist are refused in one set of words, with no
  identifier echoed, so the refusal tells nothing of which (rule 3).
- **A reader sees only what they may see.** The order is read through the same listing: a link
  that names a pipeline the reader may not see is not shown, and a pipeline left with no link is
  not shown at all (an empty entry would say it runs after something unnamed). No count of what
  is left out is anywhere in the answer (rules 3 and 7).
- **A save keeps what the saver cannot see.** A save replaces the links among the pipelines the
  saver sees; a link that names a pipeline they cannot see stays as it was, so another unit's
  order is not undone by a save that never showed it.
- **A cycle is looked for among what the saver sees, and only that.** Refusing a link because a
  path exists through a pipeline the saver cannot see would tell them that such a path exists
  (rule 3: a path through nodes they may not see). So a cycle that only closes through hidden
  pipelines is not refused; the run, which reads the order whole, never runs a pipeline that is
  in a cycle.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol

import asyncpg

from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from schemas.run_order import RunOrderEntry, RunOrderView


class RunOrderRefused(Exception):
    """A save refused in words, before anything was written. `status` is 409 for a stale number
    (the conflict answer the domain model's draft gives) and 422 for an order that cannot be (a
    cycle, a pipeline not the saver's to name)."""

    def __init__(self, words: str, *, status: int = 409, error: str = "run_order_refused") -> None:
        super().__init__(words)
        self.status = status
        self.error = error


@dataclass(frozen=True)
class StoredRunOrder:
    """One saved version of a dataset's order, whole (every link, whoever may see it)."""

    dataset_id: str
    version: int
    saved_by: str
    saved_at: datetime
    runs_after: dict[str, list[str]]


class RunOrderStore(Protocol):
    async def current(self, dataset_id: str) -> StoredRunOrder | None: ...
    async def versions(self, dataset_id: str) -> list[StoredRunOrder]: ...
    async def save(
        self,
        dataset_id: str,
        runs_after: Mapping[str, list[str]],
        principal: Principal,
        *,
        expected_version: int,
    ) -> StoredRunOrder: ...


# --------------------------------------------------------------------------------- the rules


def refuse_a_stale_number(current: StoredRunOrder | None, expected_version: int) -> None:
    """A save is made from the number its person read; any other number, behind or ahead, is
    refused in words that give the number it is now, who saved it and when, and carry nothing of
    what is in it."""
    now = 0 if current is None else current.version
    if expected_version == now:
        return
    if current is None:
        raise RunOrderRefused(
            f"you meant version {expected_version} of the run order, but none has been saved "
            "(it is now version 0): read it again before changing it"
        )
    saved = current.saved_at.astimezone(UTC).strftime("%d %B %Y at %H:%M UTC")
    raise RunOrderRefused(
        f"you meant version {expected_version} of the run order, but it is now version {now}, "
        f"saved by {current.saved_by} on {saved}: read it again before changing it"
    )


def pipelines_in_a_cycle(runs_after: Mapping[str, Iterable[str]]) -> set[str]:
    """Every pipeline that is in a cycle of the links: one in a strongly connected component of
    two or more, or one that runs after itself. A pipeline that merely runs after a cycle is not
    in it. Iterative (Tarjan), so a long chain cannot exhaust the stack."""
    graph = {p: list(after) for p, after in runs_after.items()}
    for after in list(graph.values()):
        for q in after:
            graph.setdefault(q, [])
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: set[str] = set()
    counter = 0
    for root in graph:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, at = work.pop()
            if at == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            successors = graph[node]
            advanced = False
            for i in range(at, len(successors)):
                nxt = successors[i]
                if nxt not in index:
                    work.append((node, i + 1))
                    work.append((nxt, 0))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in graph[node]:
                    found.update(component)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return found


def refuse_a_cycle(runs_after: Mapping[str, Iterable[str]], labels: Mapping[str, str]) -> None:
    """Refuses links with a cycle in them, in words naming the pipelines in it by the label the
    Studio shows."""
    in_cycle = pipelines_in_a_cycle(runs_after)
    if not in_cycle:
        return
    names = sorted({labels.get(p, "an unnamed pipeline") for p in in_cycle}, key=str.casefold)
    quoted = ", ".join(f"“{name}”" for name in names)
    raise RunOrderRefused(
        "This order cannot be saved: each of these pipelines would run after itself, directly "
        f"or through the others: {quoted}. Remove one of the links between them.",
        status=422,
        error="run_order_cycle",
    )


#: One set of words for every reason a pipeline is not one the saver may name (rule 3).
NOT_THIS_DATASETS_PIPELINE = (
    "This order names a pipeline that is not one of this dataset's pipelines. "
    "Reload the page and set the order again."
)


def pipelines_of(
    recipes: Iterable[StudioRecipeDraft], dataset_id: str
) -> dict[str, StudioRecipeDraft]:
    """The pipelines of the dataset as the person reads them: those the listing gave them (it
    reads as the person), placed in this dataset, and not a previous version. Deployed or not."""
    return {
        r.recipe_id: r
        for r in recipes
        if r.dataset_id == dataset_id and r.status is not StudioRecipeStatus.SUPERSEDED
    }


def _once(ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def links_the_reader_sees(
    stored: Mapping[str, Iterable[str]], visible: Collection[str]
) -> dict[str, list[str]]:
    """The links among the pipelines in `visible`, and no pipeline left with none."""
    shown: dict[str, list[str]] = {}
    for pipeline, after in stored.items():
        if pipeline not in visible:
            continue
        kept = _once(q for q in after if q in visible)
        if kept:
            shown[pipeline] = kept
    return shown


def links_after_a_save(
    stored: Mapping[str, Iterable[str]],
    submitted: Mapping[str, list[str]],
    visible: Collection[str],
) -> dict[str, list[str]]:
    """What is stored after a save: the saver's links among the pipelines they see, and every
    stored link that names one they do not (the pipeline holding it, or what it runs after)
    exactly as it was."""
    merged: dict[str, list[str]] = {}
    for pipeline, after in stored.items():
        unseen = [q for q in after if pipeline not in visible or q not in visible]
        if unseen:
            merged[pipeline] = _once(unseen)
    for pipeline, after in submitted.items():
        merged[pipeline] = _once([*after, *merged.get(pipeline, [])])
    return {p: after for p, after in merged.items() if after}


def view_of(
    dataset_id: str, stored: StoredRunOrder | None, visible: Collection[str]
) -> RunOrderView:
    """The answer for a reader: the order's number, who and when, and the links they may see, in
    a fixed order."""
    if stored is None:
        return RunOrderView(dataset_id=dataset_id, version=0, entries=[])
    shown = links_the_reader_sees(stored.runs_after, visible)
    return RunOrderView(
        dataset_id=dataset_id,
        version=stored.version,
        saved_by=stored.saved_by,
        saved_at=stored.saved_at,
        entries=[RunOrderEntry(pipeline_id=p, runs_after=shown[p]) for p in sorted(shown)],
    )


async def save_run_order(
    store: RunOrderStore,
    dataset_id: str,
    principal: Principal,
    entries: Iterable[RunOrderEntry],
    *,
    expected_version: int,
    recipes: Iterable[StudioRecipeDraft],
) -> tuple[StoredRunOrder, dict[str, StudioRecipeDraft]]:
    """A save as the route makes it: the pipelines named are the saver's to name, a cycle among
    the ones they see is refused, what they cannot see is kept, and the store checks the number.
    Returns what was stored and the pipelines the saver sees."""
    visible = pipelines_of(recipes, dataset_id)
    submitted: dict[str, list[str]] = {}
    for entry in entries:
        named = [entry.pipeline_id, *entry.runs_after]
        if any(p not in visible for p in named):
            raise RunOrderRefused(NOT_THIS_DATASETS_PIPELINE, status=422)
        links = _once(entry.runs_after)
        if links:
            submitted[entry.pipeline_id] = links
    refuse_a_cycle(submitted, {p: r.label for p, r in visible.items()})
    stored = await store.current(dataset_id)
    merged = links_after_a_save({} if stored is None else stored.runs_after, submitted, visible)
    saved = await store.save(dataset_id, merged, principal, expected_version=expected_version)
    return saved, visible


# --------------------------------------------------------------------------------- the stores


class InMemoryRunOrderStore:
    """The same rules with no Postgres, for tests and a process without one. Its save has no
    await between the number's check and the write, so two saves of one number cannot both land."""

    def __init__(self) -> None:
        self._held: dict[str, list[StoredRunOrder]] = {}

    async def current(self, dataset_id: str) -> StoredRunOrder | None:
        held = self._held.get(dataset_id)
        return held[-1] if held else None

    async def versions(self, dataset_id: str) -> list[StoredRunOrder]:
        return list(self._held.get(dataset_id, []))

    async def save(
        self,
        dataset_id: str,
        runs_after: Mapping[str, list[str]],
        principal: Principal,
        *,
        expected_version: int,
    ) -> StoredRunOrder:
        held = self._held.setdefault(dataset_id, [])
        refuse_a_stale_number(held[-1] if held else None, expected_version)
        saved = StoredRunOrder(
            dataset_id=dataset_id,
            version=expected_version + 1,
            saved_by=principal.id,
            saved_at=datetime.now(UTC),
            runs_after={p: list(a) for p, a in runs_after.items()},
        )
        held.append(saved)
        return saved


def _row(row: Any) -> StoredRunOrder:
    content = row["content"]
    content = json.loads(content) if isinstance(content, str) else content
    return StoredRunOrder(
        dataset_id=row["dataset_id"],
        version=row["version"],
        saved_by=row["saved_by"],
        saved_at=row["saved_at"],
        runs_after={p: list(a) for p, a in content.get("runs_after", {}).items()},
    )


class PostgresRunOrderStore:
    """The rules above; each save in one transaction under the dataset's advisory lock, with the
    key (`dataset_id`, `version`) behind it, so two requests at once cannot both win. Every
    version is kept."""

    BOOTSTRAP_SQL: ClassVar[str] = """
    CREATE TABLE IF NOT EXISTS dataset_run_orders (
        dataset_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version >= 1),
        content JSONB NOT NULL,
        saved_by TEXT NOT NULL,
        saved_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (dataset_id, version)
    );
    """

    _COLUMNS = "dataset_id, version, content, saved_by, saved_at"

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresRunOrderStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(cls.BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def current(self, dataset_id: str) -> StoredRunOrder | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {self._COLUMNS} FROM dataset_run_orders WHERE dataset_id = $1 "
                "ORDER BY version DESC LIMIT 1",
                dataset_id,
            )
        return _row(row) if row is not None else None

    async def versions(self, dataset_id: str) -> list[StoredRunOrder]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {self._COLUMNS} FROM dataset_run_orders WHERE dataset_id = $1 "
                "ORDER BY version",
                dataset_id,
            )
        return [_row(r) for r in rows]

    async def save(
        self,
        dataset_id: str,
        runs_after: Mapping[str, list[str]],
        principal: Principal,
        *,
        expected_version: int,
    ) -> StoredRunOrder:
        saved_at = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext('dataset_run_orders:' || $1))", dataset_id
            )
            row = await conn.fetchrow(
                f"SELECT {self._COLUMNS} FROM dataset_run_orders WHERE dataset_id = $1 "
                "ORDER BY version DESC LIMIT 1",
                dataset_id,
            )
            refuse_a_stale_number(_row(row) if row is not None else None, expected_version)
            await conn.execute(
                "INSERT INTO dataset_run_orders (dataset_id, version, content, saved_by, saved_at) "
                "VALUES ($1, $2, $3::jsonb, $4, $5)",
                dataset_id,
                expected_version + 1,
                json.dumps({"runs_after": {p: list(a) for p, a in runs_after.items()}}),
                principal.id,
                saved_at,
            )
        return StoredRunOrder(
            dataset_id=dataset_id,
            version=expected_version + 1,
            saved_by=principal.id,
            saved_at=saved_at,
            runs_after={p: list(a) for p, a in runs_after.items()},
        )
