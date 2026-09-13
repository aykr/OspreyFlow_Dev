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
)
from schemas.domain import Handling


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
