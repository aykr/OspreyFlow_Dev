"""Drawn patterns as rules — the no-code typology builder (`spec/06_DECISIONS.md` ADR-109 phase D) —
against live Postgres (the saved pattern, the rule, the alert), Valkey and ArcadeDB. The pattern is
one the query builder would save: an organisation that uses a phone (new in ontology v16, so the
synthetic Ledger holds no match until an onboarding writes one).

What a mistake would do, and the case that catches it:

- a drawn typology deployed and never raising, or raising for a load that wrote nothing it matches
  (`test_a_drawn_pattern_raises_when_a_load_completes_it`), or raising the same match again on every
  load (`test_an_unchanged_match_is_not_raised_again`);
- a match larger than the rule's bound alerted on in part (rule 2)
  (`test_a_match_past_its_bound_is_refused_in_words_not_alerted_in_part`);
- a pattern no longer its deployer's still evaluated (ADR-036's "the monitor stops")
  (`test_a_pattern_no_longer_the_deployers_stops_the_rule`);
- a drawn pattern deployed to run before commit, where nothing can be matched (the schema's refusal,
  `test_a_drawn_pattern_cannot_be_deployed_before_commit`).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from services.api.config import PostgresConfig
from services.api.pattern_store import PatternStore

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from demo_fixtures.ledger import build_ledger_graph
from schemas.domain import PatternEdge, PatternNode, PatternQuery, PatternRuleParams, TypologyRuleInput
from tests.ingest.test_kyc_rules import (  # noqa: F401 - the shared fixture
    OFFICER,
    ONTOLOGY,
    SCHEME,
    _alerts,
    _application,
    _gate,
    _onboard,
    stores,
)

ORGANISATION_WITH_A_PHONE = PatternQuery(
    nodes=[PatternNode(var="o", entity_type="Organisation"), PatternNode(var="p", entity_type="Endpoint")],
    edges=[PatternEdge(edge_type="USES", from_var="o", to_var="p")],
)


async def _deployed(stores: dict[str, Any], case: str, *, max_matches: int = 200) -> tuple[Any, PatternStore]:
    patterns = await PatternStore.connect(PostgresConfig.from_env().dsn)
    saved = await patterns.save(OFFICER, pattern_id=None, name="Company with a phone",
                                definition=ORGANISATION_WITH_A_PHONE)  # fmt: skip
    rule = await stores["rules"].create(OFFICER, case, TypologyRuleInput(
        name="Drawn: company with a phone",
        params=PatternRuleParams(pattern_id=saved.pattern_id, max_matches=max_matches)))  # fmt: skip
    return rule, patterns


async def test_a_drawn_pattern_raises_when_a_load_completes_it(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule, patterns = await _deployed(stores, case)
    try:
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            await build_ledger_graph(graph=graph, ontology=ONTOLOGY, principal=OFFICER)
            gate = _gate(stores, graph, [rule], case)
            gate.patterns = patterns
            await _onboard(graph, gate, [_application("Halcyon Marine Ltd", owner_company="",
                                                      phone="447700900999")])  # fmt: skip
            (alert,) = await _alerts(stores, case)
            assert alert.typology == "pattern" and alert.trigger == "post_commit"
            assert "The drawn pattern “Company with a phone” matched 2 node(s)" in (alert.words or "")
            assert len(alert.referent_node_ids) == 2 and alert.alert_node_id is not None
    finally:
        await patterns.close()


async def test_an_unchanged_match_is_not_raised_again(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule, patterns = await _deployed(stores, case)
    try:
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            gate = _gate(stores, graph, [rule], case)
            gate.patterns = patterns
            await _onboard(graph, gate, [_application("Halcyon Marine Ltd", owner_company="",
                                                      phone="447700900999")])  # fmt: skip
            assert len(await _alerts(stores, case)) == 1
            # A second load that writes nothing the pattern matches: the old match is not raised again.
            await _onboard(graph, gate, [_application("Quiet Joinery Ltd", owner_company="")])
            assert len(await _alerts(stores, case)) == 1
    finally:
        await patterns.close()


async def test_a_match_past_its_bound_is_refused_in_words_not_alerted_in_part(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule, patterns = await _deployed(stores, case, max_matches=1)
    try:
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            gate = _gate(stores, graph, [rule], case)
            gate.patterns = patterns
            report = await _onboard(graph, gate, [_application("Halcyon Marine Ltd", owner_company="",
                                                               phone="447700900999")])  # fmt: skip
            assert await _alerts(stores, case) == []
            assert any("more than 1 nodes match" in n and "not alerted on in part" in n
                       for n in report.rule_notes)  # fmt: skip
    finally:
        await patterns.close()


async def test_a_pattern_no_longer_the_deployers_stops_the_rule(stores: dict[str, Any]) -> None:
    case = f"case-{new_id()}"
    rule, patterns = await _deployed(stores, case)
    try:
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            moved = rule.model_copy(update={"owner_id": "someone-else"})
            gate = _gate(stores, graph, [moved], case)
            gate.patterns = patterns
            known = gate.principal_for_owner

            async def as_someone_else(owner_id: str):  # type: ignore[no-untyped-def]
                found = await known(OFFICER.id)
                return found.model_copy(update={"id": "someone-else"}) if found else None

            gate.principal_for_owner = as_someone_else
            report = await _onboard(graph, gate, [_application("Halcyon Marine Ltd", owner_company="",
                                                               phone="447700900999")])  # fmt: skip
            assert await _alerts(stores, case) == []
            assert any("no longer its deployer's" in n for n in report.rule_notes)
    finally:
        await patterns.close()


def test_a_drawn_pattern_cannot_be_deployed_before_commit() -> None:
    with pytest.raises(ValidationError, match="runs after commit"):
        TypologyRuleInput(name="x", params=PatternRuleParams(pattern_id="p"), trigger="pre_commit")
