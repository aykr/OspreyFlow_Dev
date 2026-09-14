"""Handling scheme loader and evaluator — `docs/01_DOMAIN_MODEL.md` §2.2,
`docs/06_DECISIONS.md` ADR-017 (both `uk-le.yaml` and
`us-criminal-intelligence.yaml` ship)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ontology.errors import HandlingSchemeError
from ontology.handling import (
    evaluate_handling,
    load_uk_le_scheme,
    load_us_criminal_intelligence_scheme,
    principal_may_view,
)
from schemas.domain import Handling, Principal


def _handling(**overrides: object) -> Handling:
    base: dict[str, object] = {
        "classification": "OFFICIAL",
        "handling_code": "P",
        "originator": "org-1",
        "owning_unit": "org-1",
    }
    base.update(overrides)
    return Handling.model_validate(base)


def test_both_schemes_load() -> None:
    uk = load_uk_le_scheme()
    us = load_us_criminal_intelligence_scheme()
    assert uk.name == "uk-le"
    assert us.name == "us-criminal-intelligence"
    assert set(uk.handling_codes) == {"P", "C", "R"}
    assert set(us.handling_codes) == {"P", "C", "R"}


def test_evaluator_reads_booleans_not_letters() -> None:
    uk = load_uk_le_scheme()
    decision = evaluate_handling(_handling(handling_code="R"), uk)
    assert decision.dissemination == "restricted"
    assert decision.direct_action_permitted is False
    assert decision.consult_originator is False


def test_evaluator_flags_consult_originator_for_s2() -> None:
    uk = load_uk_le_scheme()
    decision = evaluate_handling(
        _handling(action_code="A1", sanitisation_code="S2"), uk
    )
    assert decision.originator_permission_required is True
    assert decision.consult_originator is True


def test_evaluator_direct_action_permitted_for_a2() -> None:
    uk = load_uk_le_scheme()
    decision = evaluate_handling(_handling(action_code="A2"), uk)
    assert decision.direct_action_permitted is True


def test_evaluator_rejects_undefined_classification() -> None:
    uk = load_uk_le_scheme()
    with pytest.raises(HandlingSchemeError):
        evaluate_handling(_handling(classification="TOP-SECRET-ALIEN-TECH"), uk)


def test_clears_true_when_principal_clearance_dominates() -> None:
    uk = load_uk_le_scheme()
    assert uk.clears("SECRET", "OFFICIAL") is True
    assert uk.clears("OFFICIAL", "OFFICIAL") is True


def test_clears_false_when_classification_exceeds_principal_clearance() -> None:
    uk = load_uk_le_scheme()
    assert uk.clears("OFFICIAL", "SECRET") is False


def test_clears_false_for_an_unrecognised_principal_clearance() -> None:
    """Default-deny, not default-allow — the same rule
    `AccessFilter.allowed_classifications` follows."""
    uk = load_uk_le_scheme()
    assert uk.clears("NOT-A-REAL-CLEARANCE", "OFFICIAL") is False


def test_clears_raises_for_an_unrecognised_classification() -> None:
    """Different in kind from an unrecognised clearance — this means the
    scheme itself does not define the marking being checked, the same
    hard error `evaluate_handling` raises for the same condition."""
    uk = load_uk_le_scheme()
    with pytest.raises(HandlingSchemeError):
        uk.clears("SECRET", "NOT-A-REAL-CLASSIFICATION")


def test_principal_may_view_permitted_record_at_sufficient_clearance() -> None:
    uk = load_uk_le_scheme()
    principal = Principal(id="p1", clearance="OFFICIAL", org_unit="unit-1")
    assert principal_may_view(_handling(), principal, uk) is True


def test_principal_may_view_denies_insufficient_classification_clearance() -> None:
    uk = load_uk_le_scheme()
    principal = Principal(id="p1", clearance="OFFICIAL", org_unit="unit-1")
    assert principal_may_view(_handling(classification="SECRET"), principal, uk) is False


def test_principal_may_view_restricted_code_requires_receivable_code_and_unit() -> None:
    uk = load_uk_le_scheme()
    handling = _handling(handling_code="R", owning_unit="unit-1", originator="unit-1")

    outsider = Principal(id="p1", clearance="SECRET", org_unit="unit-2")
    assert principal_may_view(handling, outsider, uk) is False

    wrong_unit_but_receivable = Principal(
        id="p2", clearance="SECRET", org_unit="unit-2", receivable_handling_codes=["R"]
    )
    assert principal_may_view(handling, wrong_unit_but_receivable, uk) is False

    right_unit_and_receivable = Principal(
        id="p3", clearance="SECRET", org_unit="unit-1", receivable_handling_codes=["R"]
    )
    assert principal_may_view(handling, right_unit_and_receivable, uk) is True


def test_principal_may_view_ignores_action_and_sanitisation_codes() -> None:
    """`01_DOMAIN_MODEL.md` §2.2: neither ever gates a read."""
    uk = load_uk_le_scheme()
    principal = Principal(id="p1", clearance="OFFICIAL", org_unit="unit-1")
    handling = _handling(action_code="A1", sanitisation_code="S2")
    assert principal_may_view(handling, principal, uk) is True


def test_evaluator_is_scheme_agnostic_between_uk_and_us() -> None:
    """The same evaluator, unmodified, works for either scheme — the point of
    ADR-017's two-scheme requirement."""
    us = load_us_criminal_intelligence_scheme()
    decision = evaluate_handling(
        _handling(
            classification="LAW-ENFORCEMENT-SENSITIVE",
            handling_code="C",
            sanitisation_code="S2",
            review_date=datetime.now(UTC).date(),
            legal_basis="reasonable suspicion of criminal activity",
        ),
        us,
    )
    assert decision.dissemination == "conditional"
    assert decision.consult_originator is True
