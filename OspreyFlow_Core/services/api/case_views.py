"""Case views: saved lenses on one case (ADR-144; `01_DOMAIN_MODEL.md` §2.2c; L3.2).

A view holds no data. The store keeps what a view *is* (`StoredCaseView`; the wire's `CaseView`
never names its chosen nodes or their positions). `open_view` re-reads the case each time through
the reader's own principal, already scoped to the case's read set by `get_principal`, so a view
never widens what its reader may see (ADR-099, rule 3).

**Who sees a view is decided in the store** (rule 3: access in the query, never after retrieval):
every read names the reader, and a private view of someone else is absent from the answer exactly
as a view that does not exist is. Only the creator shares or deletes; a member who can see a shared
view and is not its creator is refused in words (`NotTheViewsCreator`), since they already know it
exists.

**Live.** A view of chosen nodes reads them from the graph by id (`GraphPort.get_nodes`, filtered in
the adapter) and the links among those it may show (`edges_among`); `missing` counts the chosen
ids it could not show, for whatever reason (gone, hidden, outside the case's read set), and names
none. A filtered view narrows the reader's own projection of the case's working set, as ADR-124's
filter did. A result past the working set's cap is the typed `limit_exceeded` (rule 2).

**Collapsed at the view's own threshold** (ADR-144 decision 1 and Amendment 2; spec 03 §3.1, case
views): each node shown carries the cluster it falls in at the view's `threshold`, or at the case's
when the view has none, worked out from the `SAME_AS` and `NOT_SAME_AS` links among the shown nodes
alone, read with the reader's principal. A hidden node or link therefore never joins two shown ones
(rule 3), and a manual split holds however loose the view. The Glass collapses by these ids as it
does for the case; it applies the view's `window` to the timeline itself.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg
from pydantic import BaseModel, ConfigDict, Field
from services.resolve.projection import compute_clusters

from conduit_common.identity import new_id
from ports.graph import GraphPort
from schemas.case_views import CaseView, CaseViewInput, CaseViewOpened, NodePosition, ViewFilter
from schemas.domain import NOT_SAME_AS, SAME_AS, Edge, Interval, Node, NodeId, Principal

from .working_set.models import LimitExceededError


class StoredCaseView(BaseModel):
    """A view as the Conduit keeps it: the wire's `CaseView` plus what it never sends, the chosen
    nodes' ids and their positions (rules 3 and 7; `schemas/case_views.py`)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    case_id: str
    name: str
    created_by: str
    created_at: datetime
    shared: bool = False
    node_ids: list[NodeId] | None = None
    filter: ViewFilter | None = None
    layout: dict[NodeId, NodePosition] = Field(default_factory=dict)
    window: Interval | None = None
    threshold: float | None = None
    drawing: bool = False
    converted_from_case: str | None = None
    #: A drawing merged into a dataset (ADR-143 Amendment 2 decision 7; L3.9): the merge's load,
    #: and the drawn nodes the merge added to the selection (taken off again by its revert).
    merged_load: str | None = None
    merged_added: list[NodeId] = Field(default_factory=list)

    def wire(self) -> CaseView:
        """What a reader is sent: the selection counted, never named."""
        return CaseView(
            **self.model_dump(exclude={"node_ids", "layout", "merged_added"}),
            # A merged drawing's drawn nodes are not counted (L3.9): some may be above a reader,
            # and the merge, not its creator, chose them (rule 7; the lane review, item 13).
            chosen=len(set(self.node_ids) - set(self.merged_added))
            if self.node_ids is not None
            else None,
        )


class ViewNotFound(Exception):
    """No view by that id in the case that the reader may see: absent, someone else's private
    view, or another case's, alike (ADR-041's existence rule)."""


class NotTheViewsCreator(Exception):
    """A shared view the reader can see but did not make: only its creator shares or deletes it
    (ADR-144 decision 3)."""


class CaseViewStore(Protocol):
    async def save(
        self,
        case_id: str,
        given: CaseViewInput,
        creator: str,
        *,
        converted_from_case: str | None = None,
    ) -> StoredCaseView: ...
    async def visible_in(self, case_id: str, reader: str) -> list[StoredCaseView]: ...
    async def get(self, case_id: str, view_id: str, reader: str) -> StoredCaseView: ...
    async def share(self, case_id: str, view_id: str, reader: str) -> StoredCaseView: ...
    async def delete(self, case_id: str, view_id: str, reader: str) -> None: ...
    # Boards (ADR-143 decision 5): a view with drawing switched on, its references and layout
    # changed only by its creator; `visible_in` lists views alone, `boards_in` boards alone.
    async def save_board(
        self, case_id: str, name: str, creator: str, *, node_ids: Sequence[NodeId]
    ) -> StoredCaseView: ...
    async def boards_in(self, case_id: str, reader: str) -> list[StoredCaseView]: ...
    async def update_board(
        self,
        case_id: str,
        view_id: str,
        reader: str,
        *,
        add_node_ids: Sequence[NodeId] = (),
        layout: dict[NodeId, NodePosition] | None = None,
    ) -> StoredCaseView: ...
    #: A drawing merged (L3.9): each board of the case becomes a view (drawing off), its drawn
    #: nodes added to its selection, its layout kept and its sharing too; undone by the revert.
    async def merge_boards(
        self, case_id: str, load_id: str, drawn: Mapping[str, Sequence[NodeId]]
    ) -> int: ...
    async def unmerge_boards(self, case_id: str, load_id: str) -> int: ...


def _merged(view: StoredCaseView, load_id: str, drawn: Sequence[NodeId]) -> StoredCaseView:
    held = list(view.node_ids or [])
    added = [n for n in dict.fromkeys(drawn) if n not in held]
    return view.model_copy(
        update={"drawing": False, "merged_load": load_id, "merged_added": added,
                "node_ids": held + added}
    )  # fmt: skip


def _unmerged(view: StoredCaseView) -> StoredCaseView:
    added = set(view.merged_added)
    return view.model_copy(
        update={"drawing": True, "merged_load": None, "merged_added": [],
                "node_ids": [n for n in view.node_ids or [] if n not in added]}
    )  # fmt: skip


def _made(
    case_id: str, given: CaseViewInput, creator: str, converted_from_case: str | None
) -> StoredCaseView:
    return StoredCaseView(
        id=new_id(),
        case_id=case_id,
        name=given.name.strip() or "View",
        created_by=creator,
        created_at=datetime.now(UTC),
        node_ids=list(dict.fromkeys(given.node_ids)) if given.node_ids is not None else None,
        filter=given.filter,
        layout=dict(given.layout),
        window=given.window,
        threshold=given.threshold,
        converted_from_case=converted_from_case,
    )


def _board(case_id: str, name: str, creator: str, node_ids: Sequence[NodeId]) -> StoredCaseView:
    return StoredCaseView(
        id=new_id(),
        case_id=case_id,
        name=name.strip() or "Board",
        created_by=creator,
        created_at=datetime.now(UTC),
        node_ids=list(dict.fromkeys(node_ids)),
        drawing=True,
    )


def _updated(
    board: StoredCaseView,
    add_node_ids: Sequence[NodeId],
    layout: dict[NodeId, NodePosition] | None,
) -> StoredCaseView:
    held = list(board.node_ids or [])
    added = [n for n in dict.fromkeys(add_node_ids) if n not in held]
    return board.model_copy(
        update={
            "node_ids": held + added,
            "layout": {**board.layout, **(layout or {})},
        }
    )


def visible_to(view: StoredCaseView, reader: str) -> bool:
    """ADR-144 decision 3: its creator always; anyone else once it is shared."""
    return view.shared or view.created_by == reader


class InMemoryCaseViewStore:
    def __init__(self) -> None:
        self.views: dict[str, StoredCaseView] = {}

    async def save(
        self,
        case_id: str,
        given: CaseViewInput,
        creator: str,
        *,
        converted_from_case: str | None = None,
    ) -> StoredCaseView:
        view = _made(case_id, given, creator, converted_from_case)
        self.views[view.id] = view
        return view

    async def visible_in(self, case_id: str, reader: str) -> list[StoredCaseView]:
        return sorted(
            (
                v
                for v in self.views.values()
                if v.case_id == case_id and visible_to(v, reader) and not v.drawing
            ),
            key=lambda v: (v.created_at, v.id),
        )

    async def save_board(
        self, case_id: str, name: str, creator: str, *, node_ids: Sequence[NodeId]
    ) -> StoredCaseView:
        board = _board(case_id, name, creator, node_ids)
        self.views[board.id] = board
        return board

    async def boards_in(self, case_id: str, reader: str) -> list[StoredCaseView]:
        return sorted(
            (
                v
                for v in self.views.values()
                if v.case_id == case_id and visible_to(v, reader) and v.drawing
            ),
            key=lambda v: (v.created_at, v.id),
        )

    async def update_board(
        self,
        case_id: str,
        view_id: str,
        reader: str,
        *,
        add_node_ids: Sequence[NodeId] = (),
        layout: dict[NodeId, NodePosition] | None = None,
    ) -> StoredCaseView:
        board = await self._own(case_id, view_id, reader)
        if not board.drawing:
            raise ViewNotFound(view_id)
        changed = _updated(board, add_node_ids, layout)
        self.views[view_id] = changed
        return changed

    async def get(self, case_id: str, view_id: str, reader: str) -> StoredCaseView:
        view = self.views.get(view_id)
        if view is None or view.case_id != case_id or not visible_to(view, reader):
            raise ViewNotFound(view_id)
        return view

    async def _own(self, case_id: str, view_id: str, reader: str) -> StoredCaseView:
        view = await self.get(case_id, view_id, reader)
        if view.created_by != reader:
            raise NotTheViewsCreator(view_id)
        return view

    async def share(self, case_id: str, view_id: str, reader: str) -> StoredCaseView:
        view = (await self._own(case_id, view_id, reader)).model_copy(update={"shared": True})
        self.views[view_id] = view
        return view

    async def delete(self, case_id: str, view_id: str, reader: str) -> None:
        await self._own(case_id, view_id, reader)
        del self.views[view_id]

    async def merge_boards(
        self, case_id: str, load_id: str, drawn: Mapping[str, Sequence[NodeId]]
    ) -> int:
        boards = [v for v in self.views.values() if v.case_id == case_id and v.drawing]
        for board in boards:
            self.views[board.id] = _merged(board, load_id, drawn.get(board.id, ()))
        return len(boards)

    async def unmerge_boards(self, case_id: str, load_id: str) -> int:
        held = [v for v in self.views.values() if v.case_id == case_id and v.merged_load == load_id]
        for view in held:
            self.views[view.id] = _unmerged(view)
        return len(held)


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS case_views (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    shared BOOLEAN NOT NULL DEFAULT FALSE,
    lens JSONB NOT NULL,
    drawing BOOLEAN NOT NULL DEFAULT FALSE,
    converted_from_case TEXT
);
CREATE INDEX IF NOT EXISTS case_views_by_case ON case_views (case_id);
"""

#: The fields kept in `lens`: what the view shows and how, none of it data.
_LENS = {"node_ids", "filter", "layout", "window", "threshold", "merged_load", "merged_added"}

_COLUMNS = "id, case_id, name, created_by, created_at, shared, lens, drawing, converted_from_case"

#: Every read names its reader, so a private view of someone else is never retrieved (rule 3).
_VISIBLE = "(shared OR created_by = $2)"


def _row(row: Any) -> StoredCaseView:
    lens = row["lens"]
    lens = json.loads(lens) if isinstance(lens, str) else lens
    return StoredCaseView.model_validate(
        {
            **lens,
            "id": row["id"], "case_id": row["case_id"], "name": row["name"],
            "created_by": row["created_by"], "created_at": row["created_at"],
            "shared": row["shared"], "drawing": row["drawing"],
            "converted_from_case": row["converted_from_case"],
        }
    )  # fmt: skip


def new_view(
    case_id: str, given: CaseViewInput, creator: str, *, converted_from_case: str | None = None
) -> StoredCaseView:
    """A view as it will be stored, not yet written (for a writer holding its own transaction)."""
    return _made(case_id, given, creator, converted_from_case)


async def insert_view(conn: Any, view: StoredCaseView) -> None:
    """Writes `view` on `conn`, inside whatever transaction the caller holds (the upgrade's
    migration saves a view and retires its case in one)."""
    await conn.execute(
        f"INSERT INTO case_views ({_COLUMNS}) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
        view.id, view.case_id, view.name, view.created_by, view.created_at, view.shared,
        json.dumps(view.model_dump(mode="json", include=_LENS)), view.drawing,
        view.converted_from_case,
    )  # fmt: skip


class PostgresCaseViewStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresCaseViewStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def save(
        self,
        case_id: str,
        given: CaseViewInput,
        creator: str,
        *,
        converted_from_case: str | None = None,
    ) -> StoredCaseView:
        view = _made(case_id, given, creator, converted_from_case)
        async with self._pool.acquire() as conn:
            await insert_view(conn, view)
        return view

    async def _listed(self, case_id: str, reader: str, *, drawing: bool) -> list[StoredCaseView]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM case_views WHERE case_id = $1 AND {_VISIBLE} "
                "AND drawing = $3 ORDER BY created_at, id",
                case_id,
                reader,
                drawing,
            )
        return [_row(r) for r in rows]

    async def visible_in(self, case_id: str, reader: str) -> list[StoredCaseView]:
        return await self._listed(case_id, reader, drawing=False)

    async def boards_in(self, case_id: str, reader: str) -> list[StoredCaseView]:
        return await self._listed(case_id, reader, drawing=True)

    async def save_board(
        self, case_id: str, name: str, creator: str, *, node_ids: Sequence[NodeId]
    ) -> StoredCaseView:
        board = _board(case_id, name, creator, node_ids)
        async with self._pool.acquire() as conn:
            await insert_view(conn, board)
        return board

    async def update_board(
        self,
        case_id: str,
        view_id: str,
        reader: str,
        *,
        add_node_ids: Sequence[NodeId] = (),
        layout: dict[NodeId, NodePosition] | None = None,
    ) -> StoredCaseView:
        async with self._pool.acquire() as conn, conn.transaction():
            board = await self._own(conn, case_id, view_id, reader)
            if not board.drawing:
                raise ViewNotFound(view_id)
            changed = _updated(board, add_node_ids, layout)
            await conn.execute(
                "UPDATE case_views SET lens = $3 WHERE id = $1 AND created_by = $2 AND drawing",
                view_id,
                reader,
                json.dumps(changed.model_dump(mode="json", include=_LENS)),
            )
        return changed

    async def _fetch(self, conn: Any, case_id: str, view_id: str, reader: str) -> StoredCaseView:
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM case_views WHERE case_id = $1 AND {_VISIBLE} AND id = $3",
            case_id,
            reader,
            view_id,
        )
        if row is None:
            raise ViewNotFound(view_id)
        return _row(row)

    async def get(self, case_id: str, view_id: str, reader: str) -> StoredCaseView:
        async with self._pool.acquire() as conn:
            return await self._fetch(conn, case_id, view_id, reader)

    async def _own(self, conn: Any, case_id: str, view_id: str, reader: str) -> StoredCaseView:
        view = await self._fetch(conn, case_id, view_id, reader)
        if view.created_by != reader:
            raise NotTheViewsCreator(view_id)
        return view

    async def share(self, case_id: str, view_id: str, reader: str) -> StoredCaseView:
        async with self._pool.acquire() as conn, conn.transaction():
            view = await self._own(conn, case_id, view_id, reader)
            await conn.execute(
                "UPDATE case_views SET shared = TRUE WHERE id = $1 AND created_by = $2",
                view_id,
                reader,
            )
        return view.model_copy(update={"shared": True})

    async def delete(self, case_id: str, view_id: str, reader: str) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await self._own(conn, case_id, view_id, reader)
            await conn.execute(
                "DELETE FROM case_views WHERE id = $1 AND created_by = $2", view_id, reader
            )

    async def _rewrite(self, conn: Any, view: StoredCaseView) -> None:
        await conn.execute(
            "UPDATE case_views SET lens = $2, drawing = $3 WHERE id = $1",
            view.id, json.dumps(view.model_dump(mode="json", include=_LENS)), view.drawing,
        )  # fmt: skip

    async def merge_boards(
        self, case_id: str, load_id: str, drawn: Mapping[str, Sequence[NodeId]]
    ) -> int:
        async with self._pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM case_views WHERE case_id = $1 AND drawing FOR UPDATE",
                case_id,
            )
            for row in rows:
                board = _row(row)
                await self._rewrite(conn, _merged(board, load_id, drawn.get(board.id, ())))
        return len(rows)

    async def unmerge_boards(self, case_id: str, load_id: str) -> int:
        async with self._pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM case_views WHERE case_id = $1 AND NOT drawing "
                "AND lens->>'merged_load' = $2 FOR UPDATE",
                case_id,
                load_id,
            )
            for row in rows:
                await self._rewrite(conn, _unmerged(_row(row)))
        return len(rows)


# --- opening a view -------------------------------------------------------------------------


class _Projection(Protocol):
    async def filtered_view(
        self, case_id: str, principal: Principal, keeps: ViewFilter
    ) -> tuple[list[Node], list[Edge]]: ...

    async def get_resolution_threshold(self, investigation_id: str) -> float: ...


async def _read_selection(
    graph: GraphPort, node_ids: Sequence[NodeId], principal: Principal
) -> tuple[list[Node], list[Edge]]:
    """The chosen nodes the reader may see, read now, and the links among them they may see: both
    filtered in the adapter (rule 3)."""
    nodes = await graph.get_nodes(list(node_ids), principal)
    edges = await graph.edges_among([n.id for n in nodes], principal) if len(nodes) > 1 else []
    return nodes, edges


async def _matches(
    graph: GraphPort, node_ids: Sequence[NodeId], principal: Principal
) -> tuple[list[NodeId], list[Edge]]:
    """The nodes to cluster and the resolution links among them: the shown nodes alone, and only
    the links between two of them the reader may see, filtered in the adapter (rule 3)."""
    ids = list(node_ids)
    if len(ids) < 2:
        return ids, []
    return ids, await graph.edges_among(ids, principal, edge_types=[SAME_AS, NOT_SAME_AS])


async def _collapsed(
    graph: GraphPort, nodes: list[Node], principal: Principal, tau: float
) -> list[Node]:
    """`nodes`, each annotated with its cluster at `tau` among the shown nodes."""
    ids, links = await _matches(graph, [n.id for n in nodes], principal)
    clusters = compute_clusters(
        ids,
        [e for e in links if e.type == SAME_AS],
        [e for e in links if e.type == NOT_SAME_AS],
        tau,
    )
    return [
        n.model_copy(
            update={"resolution": n.resolution.model_copy(update={"cluster_id": clusters[n.id]})}
        )
        for n in nodes
    ]


async def open_view(
    view: StoredCaseView,
    principal: Principal,
    *,
    graph: GraphPort,
    working_set: _Projection,
    cap_breach: Callable[[int, int], Any],
) -> CaseViewOpened:
    """ADR-144 decision 2: the view's case re-read now, as `principal` may see it."""
    if view.node_ids is not None:
        nodes, edges = await _read_selection(graph, view.node_ids, principal)
        # A merged drawing's drawn nodes (`merged_added`) are shown when the reader may see them
        # and never counted when not, as on the board they came from (rule 7).
        added = set(view.merged_added)
        missing = len(set(view.node_ids) - added) - sum(1 for n in nodes if n.id not in added)
    else:
        assert view.filter is not None  # one lens, exactly (`CaseViewInput`)
        nodes, edges = await working_set.filtered_view(view.case_id, principal, view.filter)
        missing = 0
    breach = cap_breach(len(nodes), len(edges))
    if breach is not None:
        raise LimitExceededError(breach)
    tau = (
        view.threshold
        if view.threshold is not None
        else await working_set.get_resolution_threshold(view.case_id)
    )
    nodes = await _collapsed(graph, nodes, principal, tau)
    shown = {n.id for n in nodes}
    layout = {k: v for k, v in view.layout.items() if k in shown}
    return CaseViewOpened(
        view=view.wire(), nodes=nodes, edges=edges, layout=layout, missing=missing
    )
