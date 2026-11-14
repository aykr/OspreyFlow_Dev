"""A shared in-memory stand-in for the part of ArcadeDB the edge-weight path reads and writes.

It answers as the real one does where it matters (it refuses a query it does not recognise, and
computes every answer from the edges actually written), so a test that carries a total or an
aggregate wrongly sees different stored components, and a different weight too under weights
version 1 only (the corpus counts reach the weight through gamma, which is 0 from version 2,
ADR-123). Used by the tests of `upsert_edges`' per-call total and
of the shared merge rules (ADR-056 Amendment 22, ADR-058).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from adapters.graph_arcadedb import adapter as adapter_module
from adapters.graph_arcadedb.naming import physical_type_name
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, Provenance, ProvenanceState, SourceRef

EDGE_TYPE = "TRANSACTED"
NODE_TYPE = "Endpoint"


#: Words ArcadeDB's SQL grammar reserves, which cannot name a bound parameter (`:after` is refused with
#: "no viable alternative"): a fake of the store must refuse them too (rule 15), or a statement the
#: real store rejects passes here.
RESERVED_PARAMETER_NAMES = frozenset(
    {
        "after", "before", "from", "to", "order", "limit", "select", "where", "set", "update",
        "insert", "into", "delete", "remove", "and", "or", "not", "in", "by", "skip", "as", "is",
        "null", "true", "false",
    }
)  # fmt: skip


#: A Gremlin lookup by our `id` property that starts the traversal from the whole store: ArcadeDB
#: answers it by scanning every element, labelled or not (ADR-124 Amendment 2 measured 3.6 s for
#: 1,000 ids at 200,000 vertices), so a load that sends one per item grows with the graph's square.
#: The stand-in refuses it (rule 15: what the real store does badly enough to fail a load at size,
#: it refuses), so the write path must resolve ids through each type's unique `id` index by SQL
#: and start from record ids (ADR-124 Amendment 18).
#: Any filter steps may come first (`g.V().has("reverted",false).has("id",…)` still reads the whole
#: store), and the property may be quoted either way.
_SCANS = re.compile(r"""(^g|\.)(V|E)\(\)(\.(hasLabel|has|hasNot)\([^)]*\))*?\.has\((["'])id\5""")


def refuse_scans(query: str) -> None:
    """Refused wherever it starts a traversal: at the head of the query, or mid-way (`.V().has("id",
    …)`, which also reads the whole store)."""
    if _SCANS.search(query):
        raise AssertionError(f"a lookup by id that scans the whole store (ADR-124 Am 18): {query}")


def refuse_reserved_parameters(command: str) -> None:
    for name in re.findall(r"(?<![\w:]):(\w+)", command):
        if name.lower() in RESERVED_PARAMETER_NAMES:
            raise AssertionError(
                f"ArcadeDB refuses `:{name}` as a parameter name (a reserved word): {command}"
            )


class CountingStore:
    """In-memory stand-in for the part of ArcadeDB the weight path reads and writes."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.sql_sent: list[tuple[str, dict[str, Any]]] = []
        #: The first link written for each pair; `links` has every link, since a pair may hold
        #: several (ADR-102 Amendment 3: one link per audience).
        self.edges: dict[tuple[str, str], dict[str, Any]] = {}
        self.links: list[dict[str, Any]] = []
        #: Every vertex id asked for is a vertex of `NODE_TYPE` (the stand-in stores no vertices),
        #: each with a record id of its own, as ArcadeDB gives one.
        self._vertex_rids: dict[str, str] = {}
        #: Links ArcadeDB holds twice, whose `id` index answers with the stray second record, which
        #: no traversal reaches (ADR-056 Amendments 15, 16 and 19): a write by that record id is
        #: kept there, and no read sees it.
        self.strays: dict[str, dict[str, Any]] = {}

    def vertex_rid(self, node_id: str) -> str:
        return self._vertex_rids.setdefault(node_id, f"#1:{len(self._vertex_rids)}")

    def vertex_id(self, rid: str) -> str:
        found = [i for i, r in self._vertex_rids.items() if r == rid]
        if not found:
            raise AssertionError(f"no vertex at {rid!r}: a record id the store never gave")
        return found[0]

    @staticmethod
    def _counts(edge: dict[str, Any], query: str) -> bool:
        """Whether a count query sees this edge, as the real store answers it: a link with
        `superseded_by` is left out only if the query says `hasNot("superseded_by")`, so a query
        that forgot the step still counts it (ADR-120 Amendment 5)."""
        return not ('hasNot("superseded_by")' in query and edge.get("superseded_by"))

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        """The SQL the adapter sends here: which of `ids` a type's unique `id` index holds, so a new
        link's id is checked by the index and not by a scan of the type; and the removal of a
        link's flattened `valid_to` when a merge leaves its span open (ADR-127 decision 11)."""
        self.sql_sent.append((command, dict(params or {})))
        refuse_reserved_parameters(command)
        removal = re.fullmatch(r"UPDATE `(\w+)` REMOVE valid_to WHERE id = :id", command)
        if removal is not None and params is not None:
            # The one removal the adapter makes: a link's flattened end, found by its unique id.
            for link in self.links:
                if link["id"] == params["id"]:
                    link.pop("valid_to", None)
            return []
        if command == "SELECT name, type, indexes FROM schema:types":
            unique_id = [{"unique": True, "properties": ["id"]}]
            return [
                {"name": physical_type_name(NODE_TYPE), "type": "vertex", "indexes": unique_id},
                {"name": physical_type_name(EDGE_TYPE), "type": "edge", "indexes": unique_id},
            ]
        lookup = re.fullmatch(r"SELECT @rid AS rid, id FROM `(\w+)` WHERE id IN :ids", command)
        if lookup is not None and params is not None:
            if lookup.group(1) == physical_type_name(NODE_TYPE):
                return [{"rid": self.vertex_rid(i), "id": i} for i in params["ids"]]
            return [
                {"rid": f"#9:{n}" if link["id"] in self.strays else f"#2:{n}", "id": link["id"]}
                for n, link in enumerate(self.links)
                if link["id"] in params["ids"]
            ]
        match = re.fullmatch(r"SELECT id FROM `(\w+)` WHERE id IN :ids", command)
        if match is None or params is None:
            raise AssertionError(f"unexpected SQL: {command}")
        held = {link["id"] for link in self.links}
        return [{"id": i} for i in params["ids"] if i in held]

    def corpus_total_queries(self) -> int:
        return sum(1 for q in self.queries if q.startswith("g.V().outE("))

    async def gremlin(
        self, query: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[Any]:
        self.queries.append(query)
        refuse_scans(query)
        if query.startswith("g.V().outE("):  # the corpus total, one whole-corpus traversal
            seen = [e for e in self.edges.values() if self._counts(e, query)]
            return [{"result": sum(e["occurrences"] for e in seen)}]
        if ".elementMap()" in query:  # an existing edge for this pair, from its source's record
            quoted = literals(query)  # source's record id, label, reverted, superseded_by, id, target
            src, tgt = self.vertex_id(quoted[0]), quoted[-1]
            # As the real store answers it: a link marked reverted or superseded is left out only if
            # the query says so, so a query that forgot the step would still find it.
            return [
                link
                for link in self.links
                if (link["_src"], link["_tgt"]) == (src, tgt)
                and not ('has("reverted",false)' in query and link.get("reverted"))
                and not ('hasNot("superseded_by")' in query and link.get("superseded_by"))
            ]

        if ".values(" in query and ".sum()" in query:  # one vertex's own weighted degree
            vertex = self.vertex_id(literals(query)[0])
            # `bothE()` reads a link from a node to itself back twice, so it counts twice here.
            return [
                {
                    "result": sum(
                        e["occurrences"] * ((s == vertex) + (t == vertex))
                        for (s, t), e in self.edges.items()
                        if self._counts(e, query)
                    )
                }
            ]
        if ".addE(" in query:
            assert params is not None
            record = {key.removeprefix("prop_"): value for key, value in params.items()}
            if any(link["id"] == record["id"] for link in self.links):
                # Edge `id` is UNIQUE per type (`schema.py`): the real store refuses the write.
                raise AssertionError(f"duplicate edge id {record['id']!r}: the unique index refuses")
            src, tgt = self.vertex_id(params["src"]), self.vertex_id(params["tgt"])
            record["_src"], record["_tgt"] = src, tgt
            self.links.append(record)
            self.edges.setdefault((src, tgt), record)
            return []
        # A merge into an existing edge, by the record id its own type's index gave (ADR-110
        # Amendment 18, ADR-124 Amendment 18).
        stray = re.match(r"g\.E\('#9:(\d+)'\)", query)
        if stray is not None and params is not None:
            # Written onto the stray second record: kept there, read by nothing.
            self.strays[self.links[int(stray.group(1))]["id"]].update(params)
            return []
        through = re.match(r"g\.V\('(#1:\d+)'\)\.(outE|bothE)\('\w+'\)\.has\(\"id\",'([^']+)'\)\.property", query)
        if through is not None and params is not None:
            # A merge into the link a traversal reaches from its source (ADR-124 Amendment 18).
            vertex = self.vertex_id(through.group(1))
            reached = [
                link for link in self.links
                if link["id"] == through.group(3)
                and (link["_src"] == vertex or (through.group(2) == "bothE" and link["_tgt"] == vertex))
            ]  # fmt: skip
            assert reached, f"no link {through.group(3)!r} at {vertex!r}"
            for record in reached:
                record.update({k.removeprefix("prop_"): v for k, v in params.items()})
            return []
        merge = re.match(r"g\.E\('#2:(\d+)'\)", query)
        if merge is not None:
            assert params is not None
            record = self.links[int(merge.group(1))]
            assert record["id"] == params["prop_id"], "the record id names another link"
            record.update({k.removeprefix("prop_"): v for k, v in params.items()})
            return []
        raise AssertionError(f"unexpected query: {query}")


def literals(query: str) -> list[str]:
    """Every quoted literal in `query` (the adapter writes ids single-quoted), in order."""
    return [m.group(2) for m in re.finditer(r"([\"'])(.*?)\1", query)]


def make_edge(source: str, target: str, n: int) -> EdgeWrite:
    now = datetime.now(UTC)
    return EdgeWrite(
        id=f"edge-{n}",
        type=EDGE_TYPE,
        source=source,
        target=target,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator=f"row-{n}", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
        ),
        created_by="test",
        created_at=now,
    )


def make_adapter(
    store: CountingStore, weight_rules: Any = None
) -> adapter_module.GraphArcadeDBAdapter:
    """`weight_rules` pins a version of the weights file (ADR-123); none takes the latest."""
    graph = adapter_module.GraphArcadeDBAdapter(
        store,  # type: ignore[arg-type]
        load_uk_le_scheme(),
        weight_rules=weight_rules,
    )
    # `apply_schema` creates types in a live store; the weights only need the ontology in place.
    graph._schema = load_default_ontology()
    return graph


def without_clock(components: Any) -> Any:
    """`computed_at` is the call's own clock reading, so it differs between calls by design."""
    as_dict = dict(components if isinstance(components, dict) else components.model_dump())
    as_dict.pop("computed_at", None)
    return as_dict


def weights(store: CountingStore) -> dict[tuple[str, str], tuple[Any, Any, Any]]:
    return {
        pair: (e["occurrences"], e["weight"], without_clock(e["weight_components"]))
        for pair, e in store.edges.items()
    }
