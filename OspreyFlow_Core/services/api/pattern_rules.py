"""Drawn patterns as rules — the no-code typology builder (`06_DECISIONS.md` ADR-109 phase D).

**Built on the query builder, not beside it.** A typology is drawn in the visual query builder
(ADR-030/032, ADR-100 Amendment 7's widened pattern language) and saved as a `SavedPattern`; an
Author deploys it as a `pattern` rule (ruling 4). Nothing here compiles anything: the pattern
language is the query builder's, and `GraphPort.match` is the one matcher.

**As the deployer, afresh.** At each evaluation the saved pattern is read again as its
deployer (`PatternStore.get_authorized`, ADR-036's discipline for monitors) — an edited pattern is
evaluated as it now reads, and one no longer theirs stops the rule, audited — and matched through
the store with the deployer's access (rule 3). **One alert per distinct match:** the finding's
signature is the matched nodes and links, so an unchanged match is not raised again, and a changed
one — by this load or by any write since — is. (A check that the match touched this load's writes
was built, shown by its own plant to decide nothing the signature did not, and removed: it would
only have hidden a match completed by another write.) **Never in part (rule 2):** a match of more
than `max_matches` nodes is refused in words.
"""

from __future__ import annotations

from collections.abc import Sequence

from ports.graph import GraphPort
from schemas.domain import EdgeWrite, NodeWrite, PatternRuleParams, Principal, TypologyRule

from .pattern_store import PatternNotFoundError, PatternStore
from .rule_evaluation import Finding


async def judge_pattern(
    rule: TypologyRule,
    deployer: Principal,
    written: Sequence[NodeWrite | EdgeWrite],
    *,
    graph: GraphPort,
    patterns: PatternStore | None,
) -> list[Finding]:
    params = rule.params
    assert isinstance(params, PatternRuleParams)
    if patterns is None:
        raise RuntimeError("this run has no pattern store to read the drawn pattern from")
    try:
        saved = await patterns.get_authorized(params.pattern_id, deployer)
    except PatternNotFoundError:
        raise RuntimeError(
            "the drawn pattern is no longer its deployer's to read; the rule cannot run"
        ) from None
    counted = await graph.match_count(saved.definition, deployer, ceiling=params.max_matches + 1)
    if counted > params.max_matches:
        raise RuntimeError(
            f"more than {params.max_matches} nodes match “{saved.name}”; not alerted on in part"
        )
    if counted == 0:
        return []
    matched = await graph.match(saved.definition, deployer)
    node_ids = sorted(n.id for n in matched.nodes)
    edge_ids = sorted(e.id for e in matched.edges)
    named = [str(n.properties.get("name") or n.properties.get("family_name") or n.type)
             for n in sorted(matched.nodes, key=lambda n: n.id)]  # fmt: skip
    shown = ", ".join(named[:5]) + (f" and {len(named) - 5} more" if len(named) > 5 else "")
    return [
        Finding(
            rule=rule,
            deployer=deployer,
            typology="pattern",
            subject=params.pattern_id,
            refs=(*node_ids, *edge_ids),
            words=f"The drawn pattern “{saved.name}” matched {len(node_ids)} node(s): {shown}",
            node_ids=node_ids,
            edge_ids=edge_ids,
        )
    ]


__all__ = ["judge_pattern"]
