"""A rule's files to the standards, exported and imported through the real app's routes
(`spec/06_DECISIONS.md` ADR-146 decision 3; rule 4: every read path gets an access-control test).

The rules store is a fake that refuses what the real one refuses (rule 15): `get_listed` finds a
rule only in its own case and only within the reader's datasets, as the real `WHERE` does
(`typology_rules.py`, `reach_clause`); the real store's own refusal is proved live in
`tests/ingest/test_rule_standards_routes_live.py`.

What a mistake would do, and the case that catches it:
- export reachable without the right, the place or a level: `test_export_needs_the_right_the_place_and_the_case`;
- another case's rule, or one outside the reader's reach, told apart from a missing one:
  `test_a_rule_the_reader_may_not_see_is_the_same_404_as_a_missing_one`;
- import reachable without `author_rules` or the Author level: `test_import_needs_author_rules_and_the_author_level`;
- a dataset outside the case told apart from one that does not exist:
  `test_a_dataset_outside_the_case_is_refused_as_a_missing_one`;
- a file read past the cap: `test_a_file_over_the_cap_is_refused_before_it_is_read`;
- an import that writes, or names an element it refused vaguely: `test_an_unsupported_file_is_refused_by_name_and_nothing_is_written`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rule_standards import to_bpmn, to_dmn
from services.api import rule_standards_routes
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_ontology,
    get_principal,
    get_typology_rules,
)
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.typology_rules import TypologyRuleNotFoundError

from schemas.domain import Principal, TypologyRule
from schemas.sentences import RuleSentence, SentenceRuleInput, SentenceRuleParams
from tests.services.api.test_rule_sentences import ONTOLOGY

CASE = Investigation(id="case-s", name="C", created_at=datetime(2026, 1, 1, tzinfo=UTC),
                     created_by="a", owning_unit="unit-1")  # fmt: skip
OTHER_CASE = "case-other"
DATASET = "ds-1"
HIDDEN_DATASET = "ds-hidden"


def _who(pid: str, *roles: str, datasets: list[str] | None = None) -> Principal:
    return Principal(id=pid, clearance="OFFICIAL", org_unit="unit-1", roles=list(roles),
                     datasets=[DATASET] if datasets is None else datasets)  # fmt: skip


RULE_AUTHOR = _who("au", "analyst", "rule_author")
ANALYST_AUTHOR = _who("an", "analyst")  # an Author, triage only: no author_rules
VIEWER = _who("vw", "analyst")
RULE_AUTHOR_VIEWER = _who("rv", "analyst", "rule_author")
NO_LEVEL = _who("none", "analyst", "rule_author")
REPORTS = _who("rp", "reports_viewer")

SENTENCE = RuleSentence.model_validate(
    {
        "subject": "Person",
        "conditions": [{"op": "equals", "property": "family_name", "value": "Okafor"}],
    }
)
BASE = f"/v1/investigations/{CASE.id}/rules"


def _rule(
    rid: str, *, case: str = CASE.id, dataset: str | None = DATASET, sentence: bool = True
) -> TypologyRule:
    params: Any = (
        SentenceRuleParams(pattern_id="pat", sentence=SENTENCE, max_matches=120)
        if sentence
        else {"typology": "structuring", "threshold": 10000, "window_days": 7, "minimum_count": 3}
    )
    return TypologyRule(name="Okafor & co", params=params, budget_ms=6000, id=rid, investigation_id=case,
                        owner_id="au", created_at=datetime(2026, 11, 1, tzinfo=UTC), dataset_id=dataset)  # fmt: skip


class _Cases:
    levels = {"au": AccessLevel.AUTHOR, "an": AccessLevel.AUTHOR, "vw": AccessLevel.VIEWER,
              "rv": AccessLevel.VIEWER, "rp": AccessLevel.VIEWER}  # fmt: skip

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        level = self.levels.get(principal.id)
        if investigation_id != CASE.id or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return CASE


class _Rules:
    """The real `get_listed`'s refusals: another case's rule, or one in a dataset the reader does
    not read, is not found, as a missing rule is."""

    def __init__(self) -> None:
        self.rules = {r.id: r for r in (
            _rule("r-1"), _rule("r-other", case=OTHER_CASE), _rule("r-hidden", dataset=HIDDEN_DATASET),
            _rule("r-template", sentence=False), _rule("r-whole", dataset=None),
        )}  # fmt: skip
        self.writes: list[str] = []

    async def get_listed(
        self, rule_id: str, investigation_id: str, principal: Principal
    ) -> TypologyRule:
        rule = self.rules.get(rule_id)
        if rule is None or rule.investigation_id != investigation_id:
            raise TypologyRuleNotFoundError(rule_id)
        if rule.dataset_id is not None and rule.dataset_id not in (principal.datasets or []):
            raise TypologyRuleNotFoundError(rule_id)
        return rule

    def __getattr__(self, attr: str) -> Any:
        async def refuse(*_: Any, **__: Any) -> Any:
            self.writes.append(attr)
            raise AssertionError(f"the rules store was asked to {attr}")

        return refuse


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **entry: Any) -> None:
        self.entries.append(entry)


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    things: dict[str, Any] = {"rules": _Rules(), "audit": _Audit()}
    app.dependency_overrides.update({
        get_investigations: _Cases, get_ontology: lambda: ONTOLOGY,
        get_typology_rules: lambda: things["rules"], get_audit: lambda: things["audit"],
    })  # fmt: skip
    yield things
    app.dependency_overrides.clear()


def _as(who: Principal) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: who
    return TestClient(app)


def _files(dataset: str = DATASET, rule: SentenceRuleInput | None = None) -> tuple[str, str]:
    rule = rule or SentenceRuleInput(name="Okafor", sentence=SENTENCE)
    return to_bpmn(rule, dataset_id=dataset), to_dmn(rule)


def _import(who: Principal, bpmn: str | bytes, dmn: str | bytes) -> Any:
    return _as(who).post(f"{BASE}/import", files={"bpmn": ("r.bpmn", bpmn), "dmn": ("r.dmn", dmn)})


def test_export_gives_the_two_files_of_the_rule_and_is_audited(world: dict[str, Any]) -> None:
    bpmn = _as(VIEWER).get(f"{BASE}/r-1/export.bpmn")
    assert bpmn.status_code == 200, bpmn.text
    assert bpmn.headers["content-type"].startswith("application/xml")
    assert bpmn.headers["content-disposition"] == 'attachment; filename="okafor-co.bpmn"'
    assert 'osprey:rule dataset="ds-1"' in bpmn.text and "<bpmn:businessRuleTask " in bpmn.text
    dmn = _as(VIEWER).get(f"{BASE}/r-1/export.dmn")
    assert dmn.status_code == 200 and "<dmn:decisionTable " in dmn.text
    assert [e["action"] for e in world["audit"].entries] == ["export_rule_file", "export_rule_file"]
    assert world["audit"].entries[0]["resolved_query"] == {"rule_id": "r-1", "file": "bpmn"}


def test_an_exported_rule_imports_back_to_the_same_rule(world: dict[str, Any]) -> None:
    bpmn = _as(RULE_AUTHOR).get(f"{BASE}/r-1/export.bpmn").content
    dmn = _as(RULE_AUTHOR).get(f"{BASE}/r-1/export.dmn").content
    back = _import(RULE_AUTHOR, bpmn, dmn)
    assert back.status_code == 200, back.text
    rule = world["rules"].rules["r-1"]
    assert SentenceRuleInput.model_validate(back.json()) == SentenceRuleInput(
        name=rule.name,
        sentence=rule.params.sentence,
        budget_ms=rule.budget_ms,
        max_matches=rule.params.max_matches,
    )


def test_export_needs_the_right_the_place_and_the_case(world: dict[str, Any]) -> None:
    for kind in ("bpmn", "dmn"):
        assert _as(NO_LEVEL).get(f"{BASE}/r-1/export.{kind}").status_code == 404
        refused = _as(_who("np", "no_role")).get(f"{BASE}/r-1/export.{kind}")
        assert refused.status_code == 403 and refused.json()["detail"]["error"] == "right_required"
        # The reports viewer reads the alert queue but is not offered the place (ADR-146 decision 2).
        placed = _as(REPORTS).get(f"{BASE}/r-1/export.{kind}")
        assert placed.status_code == 403 and placed.json()["detail"]["error"] == "place_required"
    assert _as(VIEWER).get(f"{BASE}/r-1/export.toml").status_code == 422
    assert "export_rule_file" not in [e["action"] for e in world["audit"].entries]


def test_a_rule_the_reader_may_not_see_is_the_same_404_as_a_missing_one(
    world: dict[str, Any],
) -> None:
    missing = _as(VIEWER).get(f"{BASE}/r-nothing/export.bpmn")
    assert missing.status_code == 404
    for rid in ("r-other", "r-hidden"):
        seen = _as(VIEWER).get(f"{BASE}/{rid}/export.bpmn")
        assert (seen.status_code, seen.json()) == (missing.status_code, missing.json()), rid
    assert "export_rule_file" not in [e["action"] for e in world["audit"].entries]


def test_a_template_rule_or_one_for_the_whole_deployment_is_refused_in_words(
    world: dict[str, Any],
) -> None:
    template = _as(VIEWER).get(f"{BASE}/r-template/export.bpmn")
    assert template.status_code == 422
    assert template.json()["detail"]["error"] == "rule_not_in_the_form"
    assert "structuring template" in template.json()["detail"]["detail"]
    whole = _as(VIEWER).get(f"{BASE}/r-whole/export.dmn")
    assert whole.status_code == 422 and whole.json()["detail"]["error"] == "rule_names_no_dataset"


def test_import_needs_author_rules_and_the_author_level(world: dict[str, Any]) -> None:
    bpmn, dmn = _files()
    assert _import(NO_LEVEL, bpmn, dmn).status_code == 404
    refused = _import(ANALYST_AUTHOR, bpmn, dmn)
    assert refused.status_code == 403 and refused.json()["detail"]["right"] == "author_rules"
    assert _import(RULE_AUTHOR_VIEWER, bpmn, dmn).status_code == 403  # an Author's
    assert _import(RULE_AUTHOR, bpmn, dmn).status_code == 200


def test_a_dataset_outside_the_case_is_refused_as_a_missing_one(world: dict[str, Any]) -> None:
    hidden = _import(RULE_AUTHOR, *_files(HIDDEN_DATASET))
    nowhere = _import(RULE_AUTHOR, *_files("ds-that-does-not-exist"))
    assert hidden.status_code == 404
    assert (hidden.status_code, hidden.json()) == (nowhere.status_code, nowhere.json())
    assert hidden.json() == {"detail": {"error": "dataset_not_found"}}
    outside = _import(_who("au", "analyst", "rule_author", datasets=[]), *_files())
    assert outside.status_code == 404


def test_a_file_over_the_cap_is_refused_before_it_is_read(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    bpmn, dmn = _files()
    read: list[bytes] = []
    real = rule_standards_routes.from_files
    monkeypatch.setattr(
        rule_standards_routes, "from_files", lambda b, d: read.append(b) or real(b, d)
    )
    padded = bpmn + " " * (rule_standards_routes.MAX_RULE_FILE_BYTES - len(bpmn) + 1)
    refused = _import(RULE_AUTHOR, padded, dmn)
    assert refused.status_code == 413 and refused.json()["detail"]["error"] == "rule_file_too_large"
    assert "256 KB" in refused.json()["detail"]["detail"]
    assert read == []
    at_the_cap = bpmn + " " * (rule_standards_routes.MAX_RULE_FILE_BYTES - len(bpmn))
    assert _import(RULE_AUTHOR, at_the_cap, dmn).status_code == 200


def test_an_unsupported_file_is_refused_by_name_and_nothing_is_written(
    world: dict[str, Any],
) -> None:
    bpmn, dmn = _files()
    planted = bpmn.replace(
        "</bpmn:businessRuleTask>", '</bpmn:businessRuleTask><bpmn:exclusiveGateway id="g"/>', 1
    )
    assert planted != bpmn
    refused = _import(RULE_AUTHOR, planted, dmn)
    assert refused.status_code == 422
    assert refused.json()["detail"]["error"] == "rule_file_unsupported"
    assert refused.json()["detail"]["unsupported"] == ["bpmn:exclusiveGateway"]
    assert "bpmn:exclusiveGateway" in refused.json()["detail"]["detail"]
    malformed = _import(RULE_AUTHOR, b"<nope", dmn)
    assert (
        malformed.status_code == 422 and malformed.json()["detail"]["error"] == "rule_file_refused"
    )
    assert world["rules"].writes == [] and world["audit"].entries == []


def test_an_imported_rule_naming_an_undeclared_property_is_refused_in_words(
    world: dict[str, Any],
) -> None:
    bad = SentenceRuleInput(name="n", sentence=RuleSentence.model_validate(
        {"subject": "Person", "conditions": [{"op": "equals", "property": "shoe_size", "value": "9"}]}))  # fmt: skip
    refused = _import(RULE_AUTHOR, *_files(rule=bad))
    assert refused.status_code == 422
    assert refused.json()["reason"] == "unknown_property"
