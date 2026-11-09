"""The deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11): `osprey.yaml`'s
`grading.scheme` (5x5x5 by default, or 3x5x2), rendered into `deployment.env` as
`OSPREY_GRADING_SCHEME`, read by the Conduit failing closed (nothing set is the default; anything
else that is not exactly a scheme stops the start), and answered at `GET /v1/grading-scheme` to
any signed-in person, as the yardstick is (`test_route_rights.py`'s row and its reference-catalogue
read), and to nobody signed out."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from harness.render import _render_env
from pydantic import ValidationError
from services.api.app import app
from services.api.config import GradingSchemeUnknown, GradingSettings

from schemas.deployment import OspreyConfig
from schemas.domain import Principal


def test_the_scheme_defaults_to_5x5x5_and_another_is_refused_at_validation() -> None:
    assert OspreyConfig().grading.scheme == "5x5x5"
    assert OspreyConfig.model_validate({"grading": {"scheme": "3x5x2"}}).grading.scheme == "3x5x2"
    with pytest.raises(ValidationError):
        OspreyConfig.model_validate({"grading": {"scheme": "4x4"}})


def test_the_scheme_is_rendered_for_the_conduit() -> None:
    assert "OSPREY_GRADING_SCHEME=5x5x5\n" in _render_env(OspreyConfig())
    chosen = OspreyConfig.model_validate({"grading": {"scheme": "3x5x2"}})
    assert "OSPREY_GRADING_SCHEME=3x5x2\n" in _render_env(chosen)


@pytest.mark.parametrize(("raw", "expected"), [(None, "5x5x5"), ("5x5x5", "5x5x5"),
                                               ("3x5x2", "3x5x2")])  # fmt: skip
def test_the_conduit_reads_the_scheme(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: str
) -> None:
    if raw is None:
        monkeypatch.delenv("OSPREY_GRADING_SCHEME", raising=False)
    else:
        monkeypatch.setenv("OSPREY_GRADING_SCHEME", raw)
    assert GradingSettings.from_env().scheme == expected


@pytest.mark.parametrize("raw", ["", "3X5X2", " 5x5x5", "4x4"])
def test_a_scheme_the_conduit_does_not_know_stops_it_rather_than_guessing(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", raw)
    with pytest.raises(GradingSchemeUnknown):
        GradingSettings.from_env()


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return Principal(id=token, clearance="OFFICIAL", org_unit="unit-1", roles=[])


def test_the_route_answers_the_scheme_and_its_grades_to_anyone_signed_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.state, "principal_resolver", _Resolver(), raising=False)
    monkeypatch.setattr(app.state, "grading", GradingSettings(scheme="3x5x2"), raising=False)
    answer = TestClient(app, headers={"Authorization": "Bearer nobody"}).get("/v1/grading-scheme")
    assert answer.status_code == 200, answer.text
    assert answer.json() == {
        "scheme": "3x5x2",
        "source": ["A", "B", "C"],
        "intelligence": ["1", "2", "3", "4", "5"],
        "handling": ["P", "C"],
    }


def test_the_route_answers_nobody_signed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.state, "principal_resolver", _Resolver(), raising=False)
    assert TestClient(app).get("/v1/grading-scheme").status_code == 401
