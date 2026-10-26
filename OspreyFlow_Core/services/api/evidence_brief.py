"""The evidence brief: the graph facts a question to the model is asked over (`06_DECISIONS.md`
ADR-129 decision 1).

It is the model's input and nothing else. (The case brief of ADR-128, `case_brief.py`, is the
analyst's list of information requirements, a different thing; the two names are kept apart.)

**What it is built from.** Only what the caller hands in: the nodes and links of the case as the
asking analyst may see them (`WorkingSetService.visible_membership`, the projection every read runs)
and the dataset labels of the case. Nothing here reads a store, so nothing here can widen what the
analyst may see; an item the analyst may not see is not in the arguments and so cannot be in the
text (rule 3). The same arguments always give the same text, in an order that depends on the items
shown alone, so the prompt over a case with a hidden item and the prompt over a copy of the case
without it are the same bytes.

**What it holds.** The scope is the selection and its one-hop neighbourhood, or, with no selection,
the whole view. The text lists every entity in scope (type, display name); every link among them as
a numbered fact `[G-n]` (type, the two ends by display name, first and last date, occurrences, the
dataset's label, direct or inferred); and the events per month over the links in scope. Path facts
are not built: a question about a connection is answered from the links.

**What the model never sees.** A node id, a link id, Gremlin or a source identifier (rule 7). The
ids a `[G-n]` stands for stay in `GraphFact`, which goes to the Glass in the answer payload and
never into the text. A display name is read from the node's properties and never falls back to a
fragment of its id.

**Never trimmed (rule 2).** The text is whole or it is not built: the caller counts it against the
budget and refuses the question when it does not fit.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from schemas.domain import Edge, Handling, Node, ProvenanceState

from .working_set.models import BranchFilter

#: The properties that name an entity, most telling first. The same order the alert queue reads,
#: restated here because its fallback (`type` plus the end of the id) would put a fragment of an id
#: in front of the model.
_NAME_PROPERTIES = (
    "name",
    "account_number",
    "value_normalised",
    "family_name",
    "title",
    "rule_id",
)

_CITATION = re.compile(r"\[G-(\d+)\]")
_MARKER = re.compile(r"( ?)\[G-(\d+)\]")


def display_name(node: Node) -> str:
    """How the model is told to call `node`: its name as the Glass reads it, never its id."""
    for key in _NAME_PROPERTIES:
        value = node.properties.get(key)
        if isinstance(value, str) and " ".join(value.split()):
            if key == "family_name":
                given = node.properties.get("given_names")
                if isinstance(given, str) and given.strip():
                    return " ".join(f"{given} {value}".split())
            return " ".join(value.split())
    return f"unnamed {node.type}"


@dataclass(frozen=True)
class GraphFact:
    """One numbered link fact and the ids it stands for, for the Glass only."""

    number: int
    node_ids: tuple[str, ...]
    link_ids: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"[G-{self.number}]"


@dataclass(frozen=True)
class EvidenceScope:
    """The nodes and links the brief is about, before it is written out."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


@dataclass(frozen=True)
class EvidenceBrief:
    """The written brief. `text` is what the model reads; everything else stays in the Conduit and
    the Glass."""

    text: str
    facts: tuple[GraphFact, ...] = ()
    #: Every node and link the text names, so an answer can be hidden from a reader who may not
    #: see one of them (rule 3).
    node_ids: tuple[str, ...] = ()
    link_ids: tuple[str, ...] = ()
    #: The handling of every element the text is drawn from, for the question's own.
    handlings: tuple[Handling, ...] = field(default_factory=tuple)

    def fact(self, number: int) -> GraphFact | None:
        for held in self.facts:
            if held.number == number:
                return held
        return None


def scope_of(
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    *,
    selected_node_ids: Collection[str] = (),
    selected_link_ids: Collection[str] = (),
    window: BranchFilter | None = None,
) -> EvidenceScope:
    """The scope of a question, from the nodes and links `nodes` and `edges` hold (the reader's own
    view): the selection and everything one link from it, or the whole view when nothing is
    selected. A link selected brings its two ends. A selected id the view does not hold (hidden or
    absent: the same) selects nothing, and a selection that selects nothing is an empty scope, not
    the whole view. `window`, when given, keeps only the links whose interval overlaps it."""
    held = {n.id: n for n in nodes}
    links = [e for e in edges if e.source in held and e.target in held]
    if window is not None:
        links = [e for e in links if window.keeps_link_in_time(e)]
    asked = bool(selected_node_ids) or bool(selected_link_ids)
    if not asked:
        in_scope = set(held)
        return EvidenceScope(*_ordered(held, in_scope, links))
    chosen = {i for i in selected_node_ids if i in held}
    for e in edges:
        if e.id in selected_link_ids and e.source in held and e.target in held:
            chosen.update((e.source, e.target))
    in_scope = set(chosen)
    for e in links:
        if e.source in chosen:
            in_scope.add(e.target)
        if e.target in chosen:
            in_scope.add(e.source)
    return EvidenceScope(*_ordered(held, in_scope, links))


def _ordered(
    held: Mapping[str, Node], in_scope: set[str], links: Sequence[Edge]
) -> tuple[tuple[Node, ...], tuple[Edge, ...]]:
    nodes = sorted((held[i] for i in in_scope), key=lambda n: (n.type, display_name(n), n.id))
    among = sorted(
        (e for e in links if e.source in in_scope and e.target in in_scope),
        key=lambda e: _fact_key(e, held),
    )
    return tuple(nodes), tuple(among)


def _fact_key(edge: Edge, held: Mapping[str, Node]) -> tuple[str, str, str, str, str]:
    return (
        edge.type,
        display_name(held[edge.source]),
        display_name(held[edge.target]),
        edge.interval.valid_from.isoformat() if edge.interval else "",
        edge.id,
    )


def _day(when: datetime | None) -> str:
    return when.date().isoformat() if when is not None else "not recorded"


def _fact_line(
    number: int, edge: Edge, held: Mapping[str, Node], dataset_labels: Mapping[str, str]
) -> str:
    labels = sorted({dataset_labels[d] for d in edge.datasets if d in dataset_labels})
    first = edge.interval.valid_from if edge.interval else None
    last = edge.interval.valid_to if edge.interval else None
    source, target = held[edge.source], held[edge.target]
    if edge.provenance.state is ProvenanceState.ASSERTED:
        standing = "direct"
    else:
        standing = edge.provenance.state.value
    return (
        f"[G-{number}] {source.type} {display_name(source)} -{edge.type}-> "
        f"{target.type} {display_name(target)}; {standing}; "
        f"{edge.occurrences} occurrence{'' if edge.occurrences == 1 else 's'}; "
        f"first {_day(first)}, last {_day(last)}; "
        f"dataset: {', '.join(labels) if labels else 'not recorded'}"
    )


def write_brief(
    scope: EvidenceScope,
    dataset_labels: Mapping[str, str],
    events_per_month: Sequence[tuple[str, int]] | None = None,
    event_handlings: Sequence[Handling] = (),
) -> EvidenceBrief:
    """The brief for `scope`. `events_per_month` is `(YYYY-MM, count)` over the links in scope, read
    by the caller as the analyst (an event they may not see moves no count); `None` or empty writes
    no events section. A scope holding nothing writes the empty brief, `text == ""`."""
    if not scope.nodes:
        return EvidenceBrief(text="")
    held = {n.id: n for n in scope.nodes}
    lines = ["Entities in scope:"]
    lines.extend(f"- {n.type}: {display_name(n)}" for n in scope.nodes)
    facts: list[GraphFact] = []
    if scope.edges:
        lines.append("")
        lines.append("Links among them (cite a fact by its number, as [G-n]):")
        for number, edge in enumerate(scope.edges, start=1):
            lines.append(_fact_line(number, edge, held, dataset_labels))
            facts.append(GraphFact(number, (edge.source, edge.target), (edge.id,)))
    if events_per_month:
        lines.append("")
        lines.append("Events per month on those links:")
        lines.append("; ".join(f"{month}: {count}" for month, count in events_per_month))
    return EvidenceBrief(
        text="\n".join(lines),
        facts=tuple(facts),
        node_ids=tuple(n.id for n in scope.nodes),
        link_ids=tuple(e.id for e in scope.edges),
        handlings=(
            *(n.handling for n in scope.nodes),
            *(e.handling for e in scope.edges),
            *event_handlings,
        ),
    )


def cited_numbers(answer: str, listed: Sequence[object]) -> list[int]:
    """The `[G-n]` numbers an answer cites: those marked in its words and those the model listed,
    in the order first met, each once. Integers only: a boolean or a word in the list is not a
    number."""
    found: list[int] = [int(m.group(1)) for m in _CITATION.finditer(answer)]
    found.extend(n for n in listed if isinstance(n, int) and not isinstance(n, bool))
    return list(dict.fromkeys(found))


def strip_unheld(answer: str, held_numbers: Collection[int]) -> str:
    """`answer` without any `[G-n]` marker whose number the brief does not hold (a citation the
    model invented), together with the one space before it."""

    def keep(match: re.Match[str]) -> str:
        return match.group(0) if int(match.group(2)) in held_numbers else ""

    return _MARKER.sub(keep, answer)
