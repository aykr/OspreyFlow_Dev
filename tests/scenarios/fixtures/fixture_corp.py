"""Fixture Corp (R24) — `06_DECISIONS.md` ADR-035 §C5: the shippable, `shipped`-class demo an
analyst review runs against, and the first real citizen of ADR-035's own demo-distribution
registry. This module builds the graph shape §C5 pins, in the same synthetic, seeded, in-repo
style `hmp.py`/`cdr.py` already establish — no live service needed
to construct any of it; only the path-spoke half (`build_path_spokes`) needs a real `GraphPort`
to write into, the same way `hmp_graph.py` needs one for its own graph side.

**Generator: an original, in-repo Python module, not a wrapper around AMLSim or gen-fraud-graph
— disclosed here rather than silently substituted.** ADR-035 §C5 names both as Apache-2.0
candidate generators so Fixture Corp's own output is "owned outright and carries no third-party
licence." Checked directly before writing a line of this module: neither is a PyPI package
(`pip index versions amlsim` / `gen-fraud-graph` both return "No matching distribution found") —
AMLSim in particular is a Java/Python multi-agent simulator distributed only as a source
checkout, needing its own build toolchain this project's own `scripts/` convention ("a plain,
directly-runnable module... the shape an eventual CLI subcommand would wrap, not a shortcut
around one," `CLAUDE.md`) does not extend to, and vendoring one would reintroduce exactly the
kind of hard-to-reproduce, network- and toolchain-dependent generation the HMP/CDR fixtures'
own seeded-and-exact-multiset discipline exists to avoid. Fixture Corp is therefore
**AMLSim-*shaped*, not AMLSim-generated** — the same "Enron-*shaped*, not Enron-derived"
distinction ADR-035 §C5 itself already draws for this demo — implementing the canonical fraud-ring
typology (a shell organisation plus a tight, densely-interconnected associate cluster around it,
mirroring AMLSim's own fan-in/fan-out layering rings) as 100%-owned, original code with no
third-party dependency and no personal data.

Three independent sub-fixtures, one per property ADR-035 §C5 names (path lengths and the hidden
hop share the fourth, since both need the same hub-and-spokes graph), kept structurally separate
so no test's assertion depends on another's construction — the same "no spurious correlation...
introduced by construction" discipline `hmp.py` already follows:

- `generate_resolution_persons()` — five `Person` pairs: four at empirically-checked separation
  bands (property 1: τ 0.99/0.95/0.80 producing visibly different projections), plus one pair
  with a fully non-Latin-script family name, so this fixture's own real resolution pass exercises
  the non-Latin-family-name crash fix (`services/resolve/duckdb_setup.py`) rather than leaving
  whether that fix is ever exercised an accident of what this fixture happened to contain.
- `generate_community_rings()` — three dense, disjoint fraud rings (property 2: Louvain community
  structure).
- `build_path_spokes()` — a hub with eight `ASSOCIATE_OF` spokes of length 1..8, one carrying a
  SECRET-classified shortcut (properties 3 and 4: the pathfinder's full `max_hops` range, and an
  access-control boundary that lengthens rather than removes a path).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from conduit_common.identity import new_edge_id, now_utc
from ports.graph import GraphPort
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    Provenance,
    ProvenanceState,
    SourceRef,
)

INVESTIGATION_SCOPE = "case-fixture-corp"

_HANDLING = Handling(
    classification="OFFICIAL",
    handling_code="P",
    originator="fixture-corp",
    owning_unit="fixture-corp",
)


def _provenance(label: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="fixture-corp", locator=label, excerpt_hash="")],
        first_seen=datetime.now(UTC),
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=datetime.now(UTC), created_by="fixture-corp-generator")


# --- property 1: entity resolution at three separation bands -----------------


@dataclass(frozen=True)
class ResolutionPair:
    label: str
    node_a: Node
    node_b: Node
    #: The lowest of the three detents (0.99 / 0.95 / 0.80) at which this pair's real,
    #: empirically-measured Splink score (see this module's own docstring above) first merges —
    #: `None` if the pair never merges at any of the three. The pair merges at this value and
    #: every detent *below* it (a lower τ is a laxer bar), never above.
    merges_from_tau: float | None


def _person(node_id: str, family_name: str, given_names: str, date_of_birth: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
        },
        provenance=_provenance(f"person:{node_id}"),
        handling=_HANDLING,
        audit=_audit(),
    )


def generate_resolution_persons() -> list[ResolutionPair]:
    """Five `Person` pairs, chosen empirically against the real, untrained Splink defaults this
    ontology's `resolution` block configures for `Person`
    (`jaro_winkler(family_name)`/`levenshtein(given_names)`/`exact(date_of_birth)`, blocked on
    `soundex(family_name)`/`year(date_of_birth)`) — not assumed. Scores measured directly against
    `services.resolve.resolver.resolve_entity_type` before this module was written:

    - **identical** ("Volkov, Mikhail" x2): 0.999991 — merges at Strict (0.99), Balanced (0.95)
      and Broad (0.80).
    - **close_given_name** ("Volkov, Mikael" vs "Volkov, Mikhail", same DOB): 0.981285 — merges
      at Balanced and Broad, not Strict.
    - **close_surname_and_given** ("Petrenko, Illia" vs "Petrenco, Ilia", same DOB): 0.867624 —
      merges at Broad only.
    - **shared_surname_different_person** ("Volkov, Anna" vs "Volkov, Mikhail", different DOB):
      0.0001 — never merges at any of the three detents, the negative control proving the
      mechanism does not over-merge on a bare shared surname.
    - **identical_non_latin_script** ("李, 伟" x2): 0.999991, identical to the plain-ASCII
      `identical` pair's own score, measured the same way, not assumed — the resolution pipeline
      does not merely avoid crashing on a non-Latin-script family name
      (`services/resolve/duckdb_setup.py`'s own `null_handling="special"` fix), it produces the
      same meaningful match score a Latin-script identical pair gets, since `jaro_winkler`/
      `levenshtein` compare Unicode strings directly and `soundex` returning `NULL` for this pair
      only removes it from *one* of two blocking rules — `year(date_of_birth)` still blocks it,
      so the pair is still compared. Before the fix, this pair's mere presence in the population
      being resolved would have raised `SplinkException` for the *whole* population, not only
      failed to score this one pair — `test_fixture_corp_entity_resolution_projections_differ_by_
      threshold` running at all, end to end, is itself part of what proves the fix.

    `test_fixture_corp_entity_resolution_projections_differ_by_threshold` re-derives these scores
    live against the real resolver rather than trusting the numbers above to still hold if the
    resolver's comparisons ever change — this docstring records what was true when the fixture
    was built, not a guarantee.
    """
    return [
        ResolutionPair(
            "identical",
            _person("corp-res-identical-1", "Volkov", "Mikhail", "1975-03-12"),
            _person("corp-res-identical-2", "Volkov", "Mikhail", "1975-03-12"),
            merges_from_tau=0.99,
        ),
        ResolutionPair(
            "close_given_name",
            _person("corp-res-close-given-1", "Volkov", "Mikael", "1975-03-12"),
            _person("corp-res-close-given-2", "Volkov", "Mikhail", "1975-03-12"),
            merges_from_tau=0.95,
        ),
        ResolutionPair(
            "close_surname_and_given",
            _person("corp-res-close-both-1", "Petrenko", "Illia", "1982-05-19"),
            _person("corp-res-close-both-2", "Petrenco", "Ilia", "1982-05-19"),
            merges_from_tau=0.80,
        ),
        ResolutionPair(
            "shared_surname_different_person",
            _person("corp-res-distinct-1", "Volkov", "Anna", "1990-07-01"),
            _person("corp-res-distinct-2", "Volkov", "Mikhail", "1975-03-12"),
            merges_from_tau=None,
        ),
        ResolutionPair(
            "identical_non_latin_script",
            _person("corp-res-non-latin-1", "李", "伟", "1988-11-02"),
            _person("corp-res-non-latin-2", "李", "伟", "1988-11-02"),
            merges_from_tau=0.99,
        ),
    ]


# --- property 2: Louvain community structure ----------------------------------


@dataclass(frozen=True)
class CommunityRingsResult:
    nodes: list[Node]
    edges: list[Edge]
    #: Ground truth this generator already knows — the ring a node id belongs to.
    ring_of_node_id: dict[str, int]


def _org(node_id: str, name: str) -> Node:
    return Node(
        id=node_id,
        type="Organisation",
        properties={"name": name},
        provenance=_provenance(f"org:{node_id}"),
        handling=_HANDLING,
        audit=_audit(),
    )


def _edge(edge_type: str, source: str, target: str) -> Edge:
    return Edge(
        id=f"corp-edge-{edge_type.lower()}-{source}-{target}",
        type=edge_type,
        source=source,
        target=target,
        provenance=_provenance(f"edge:{source}->{target}"),
        handling=_HANDLING,
        audit=_audit(),
    )


def generate_community_rings(rings: int = 3, members_per_ring: int = 6) -> CommunityRingsResult:
    """Three dense, disjoint "fraud rings" — the AMLSim-style typology this generator is shaped
    after (a shell `Organisation` plus a tight, fully-interconnected `Person` cluster around it).
    Every ring's own members are `ASSOCIATE_OF` every other member in the same ring and
    `MEMBER_OF` the same ring's own `Organisation`; there is no edge of any kind between two
    different rings. Louvain (`06_DECISIONS.md` ADR-029) should therefore recover exactly
    `rings` communities, each equal to one ring's own membership —
    `test_fixture_corp_exhibits_louvain_community_structure` checks the partition found matches
    this construction exactly, not merely that it finds *some* structure.
    """
    nodes: list[Node] = []
    edges: list[Edge] = []
    ring_of: dict[str, int] = {}

    for ring in range(rings):
        org_id = f"corp-ring{ring}-org"
        nodes.append(_org(org_id, f"Ring {ring} Holdings"))
        ring_of[org_id] = ring

        member_ids = [f"corp-ring{ring}-member{i}" for i in range(members_per_ring)]
        for i, member_id in enumerate(member_ids):
            nodes.append(_person(member_id, f"Ring{ring}Member{i}", "Test", "1980-01-01"))
            ring_of[member_id] = ring
            edges.append(_edge("MEMBER_OF", member_id, org_id))

        for i in range(len(member_ids)):
            for j in range(i + 1, len(member_ids)):
                edges.append(_edge("ASSOCIATE_OF", member_ids[i], member_ids[j]))

    return CommunityRingsResult(nodes=nodes, edges=edges, ring_of_node_id=ring_of)


# --- properties 3 and 4: pathfinder range, and a hidden hop that lengthens -----


@dataclass(frozen=True)
class PathSpokesResult:
    hub_id: str
    #: spoke length (1..max_length) -> the terminal node id of that spoke's own chain.
    terminal_by_length: dict[int, str]
    #: The spoke length carrying the SECRET-classified hub->terminal shortcut.
    shortcut_spoke_length: int


def _node_write(
    node_id: str, *, classification: str, family_name: str, given_names: str
) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": "1970-01-01",
        },
        provenance=_provenance(f"person:{node_id}"),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator="fixture-corp",
            owning_unit="fixture-corp",
        ),
        created_by="fixture-corp-generator",
        created_at=now_utc(),
    )


def _edge_write(edge_type: str, source: str, target: str, *, classification: str) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(),
        type=edge_type,
        source=source,
        target=target,
        provenance=_provenance(f"edge:{source}->{target}"),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator="fixture-corp",
            owning_unit="fixture-corp",
        ),
        created_by="fixture-corp-generator",
        created_at=now_utc(),
    )


async def build_path_spokes(graph: GraphPort, *, max_length: int = 8) -> PathSpokesResult:
    """Writes a hub `Person` with `max_length` (default 8, the exact ceiling
    `PathRequest.max_hops` supports — `01_DOMAIN_MODEL.md` §6.3 / `06_DECISIONS.md` ADR-033)
    `ASSOCIATE_OF` spokes of length 1..`max_length` into a real `GraphPort`. Spokes never
    reconnect to each other or to the hub a second time, so `hub -> spoke_k_terminal` has exactly
    one route, of length exactly `k`, for every `k` in `1..max_length` —
    `test_fixture_corp_path_lengths_span_the_pathfinders_max_hops_range` walks all eight.

    The length-3 spoke additionally gets a direct, SECRET-classified `ASSOCIATE_OF` shortcut from
    the hub straight to that spoke's own terminal node.
    `test_fixture_corp_hidden_hop_lengthens_rather_than_removes_the_path` demonstrates ADR-035
    §C5's fourth property — the same one
    `test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop`
    (`tests/conformance/graph_port/test_suite.py`) already proves generically — against fixture
    data an analyst can actually see rendered: an OFFICIAL-cleared principal only ever finds the
    3-hop route; a SECRET-cleared principal also finds the 1-hop shortcut, and the 3-hop route
    never disappears for either.
    """
    hub_id = "corp-path-hub"
    shortcut_spoke_length = 3

    nodes: list[NodeWrite] = [
        _node_write(hub_id, classification="OFFICIAL", family_name="Hub", given_names="Fixture")
    ]
    edges: list[EdgeWrite] = []
    terminal_by_length: dict[int, str] = {}

    for length in range(1, max_length + 1):
        previous = hub_id
        for step in range(1, length + 1):
            node_id = f"corp-path-spoke{length}-{step}"
            nodes.append(
                _node_write(
                    node_id,
                    classification="OFFICIAL",
                    family_name=f"Spoke{length}",
                    given_names=f"Node{step}",
                )
            )
            edges.append(_edge_write("ASSOCIATE_OF", previous, node_id, classification="OFFICIAL"))
            previous = node_id
        terminal_by_length[length] = previous

    edges.append(
        _edge_write(
            "ASSOCIATE_OF",
            hub_id,
            terminal_by_length[shortcut_spoke_length],
            classification="SECRET",
        )
    )

    tx = await graph.begin_transaction()
    await graph.upsert_nodes(nodes, tx)
    await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)

    return PathSpokesResult(
        hub_id=hub_id,
        terminal_by_length=terminal_by_length,
        shortcut_spoke_length=shortcut_spoke_length,
    )
