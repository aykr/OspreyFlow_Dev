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


async def test_the_conduits_start_stops_on_an_unknown_scheme_before_opening_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The start itself, not only the reader: `lifespan` reads the setting before any store is
    opened, and an unknown scheme ends it there."""
    from services.api import app as app_module

    def opened(*_: object, **__: object) -> None:
        raise AssertionError("the start went on to open the stores")

    monkeypatch.setattr(app_module, "build_run_resources", opened)
    # The Conduit's own settings, read before the scheme, need an identity provider: not here.
    monkeypatch.setattr(app_module.ApiConfig, "from_env", classmethod(lambda cls: object()))
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "4x4")
    with pytest.raises(GradingSchemeUnknown):
        async with app_module.lifespan(app):
            pass


def test_the_route_never_answers_a_default_for_a_scheme_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no setting held (an app not started through `lifespan`), the route reads the
    environment as the start does, and an unknown scheme is refused, not answered as 5x5x5."""
    monkeypatch.setattr(app.state, "principal_resolver", _Resolver(), raising=False)
    monkeypatch.delattr(app.state, "grading", raising=False)
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "4x4")
    client = TestClient(app, raise_server_exceptions=False, headers={"Authorization": "Bearer x"})
    assert client.get("/v1/grading-scheme").status_code == 500
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "3x5x2")
    assert client.get("/v1/grading-scheme").json()["scheme"] == "3x5x2"


def test_every_list_of_the_scheme_names_is_the_schemes_of_grading_parts() -> None:
    """The names are written out where a module may not import the schemas (the install answers
    depend on PyYAML alone): each copy must be exactly `GRADING_PARTS`'s."""
    import typing

    from cli.ospreyflow.answers import GRADING_SCHEMES as ANSWERS
    from services.api.config import GRADING_SCHEMES as CONDUIT

    from schemas.deployment import GradingConfig
    from schemas.domain import GRADING_PARTS

    setting = typing.get_args(GradingConfig.model_fields["scheme"].annotation)
    assert set(ANSWERS) == set(CONDUIT) == set(setting) == set(GRADING_PARTS)
