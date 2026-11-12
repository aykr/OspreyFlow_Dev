"""The deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11): `osprey.yaml`'s
`grading.scheme` (5x5x5 by default, or 3x5x2), rendered into `deployment.env` as
`OSPREY_GRADING_SCHEME`, read by the Conduit failing closed (nothing set is the default; anything
else that is not exactly a scheme stops the start), and answered at `GET /v1/grading-scheme` to
any signed-in person, as the yardstick is (`test_route_rights.py`'s row and its reference-catalogue
read), and to nobody signed out."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from harness.render import _render_env
from pydantic import ValidationError
from services.api.app import app
from services.api.config import GradingSchemeUnknown, GradingSettings

from schemas.deployment import OspreyConfig
from schemas.domain import GradingSchemeAnswer, Principal


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
    async def resolve_principal(self, token: str) -> Principal:
        return self.resolve(token)

    def resolve(self, token: str) -> Principal:
        return Principal(id=token, clearance="OFFICIAL", org_unit="unit-1", roles=[])


def test_the_route_answers_the_scheme_and_its_grades_to_anyone_signed_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.state, "principal_resolver", _Resolver(), raising=False)
    monkeypatch.setattr(app.state, "grading", GradingSettings.of("3x5x2"), raising=False)
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


def test_the_built_in_schemes_names_are_listed_once() -> None:
    """Finding 8 of the orchestrator's review: `GRADING_PARTS` (`schemas/domain.py`) is the one
    list of the built-in schemes. No other module of the product, Python or the Glass's TypeScript,
    names both as code (a tuple, a list, a dict's keys), as `config.py`, `answers.py` and the
    Glass's `boardModel.ts` once did; prose naming them inside a longer string is not a list."""
    import re

    core = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
    five, three = (re.compile(rf"""["']{n}["']""") for n in ("5x5x5", "3x5x2"))
    owners = sorted(
        str(path.relative_to(core))
        for folder in ("packages", "services", "scripts", "cli", "harness", "apps/workspace/src")
        for suffix in ("*.py", "*.ts", "*.tsx")
        for path in (core / folder).rglob(suffix)
        if not {"node_modules", ".venv", "generated"} & set(path.parts)
        and ".test." not in path.name
        and five.search(text := path.read_text(encoding="utf-8"))
        and three.search(text)
    )
    assert owners == ["packages/schemas/domain.py"], owners


FORCE = {"scheme": "force-4x3", "source": ["W", "X", "Y", "Z"], "intelligence": ["1", "2", "3"],
         "handling": ["H"]}  # fmt: skip


def test_a_scheme_file_is_read_beside_osprey_yaml_and_rendered_with_its_grades(
    tmp_path: Path,
) -> None:
    from harness.render import load_config

    (tmp_path / "grading-scheme.yaml").write_text(yaml.safe_dump(FORCE), encoding="utf-8")
    (tmp_path / "osprey.yaml").write_text("grading:\n  scheme: grading-scheme.yaml\n", "utf-8")
    config = load_config(tmp_path / "osprey.yaml")
    assert config.grading.resolved().model_dump() == FORCE
    env = _render_env(config)
    # Once, by the scheme's name: never the file's path (a second line, found at a rebase).
    assert env.count("OSPREY_GRADING_SCHEME=") == 1
    assert "OSPREY_GRADING_SCHEME=force-4x3\n" in env
    assert f"OSPREY_GRADING_GRADES={GradingSchemeAnswer(**FORCE).model_dump_json()}\n" in env  # type: ignore[arg-type]


def test_a_scheme_file_that_cannot_be_read_or_is_no_scheme_is_refused_naming_it(
    tmp_path: Path,
) -> None:
    from harness.render import load_config

    (tmp_path / "osprey.yaml").write_text("grading:\n  scheme: absent.yaml\n", "utf-8")
    with pytest.raises(ValueError, match="absent.yaml cannot be read"):
        load_config(tmp_path / "osprey.yaml")
    (tmp_path / "absent.yaml").write_text("scheme: force-4x3\nsource: [A, A]\n", "utf-8")
    with pytest.raises(ValueError, match="is not a grading scheme"):
        load_config(tmp_path / "osprey.yaml")
    # A config not read through `load_config` cannot be rendered with a file it never read.
    with pytest.raises(ValueError, match="has not been read"):
        _render_env(OspreyConfig.model_validate({"grading": {"scheme": "absent.yaml"}}))


def test_the_conduit_reads_a_scheme_files_grades_and_fails_closed_without_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "force-4x3")
    monkeypatch.delenv("OSPREY_GRADING_GRADES", raising=False)
    with pytest.raises(GradingSchemeUnknown, match="OSPREY_GRADING_GRADES is unset"):
        GradingSettings.from_env()
    monkeypatch.setenv("OSPREY_GRADING_GRADES", GradingSchemeAnswer(**FORCE).model_dump_json())  # type: ignore[arg-type]
    assert GradingSettings.from_env().grades.model_dump() == FORCE
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "other-scheme")
    with pytest.raises(GradingSchemeUnknown, match="not other-scheme's"):
        GradingSettings.from_env()
    monkeypatch.setenv("OSPREY_GRADING_SCHEME", "force-4x3")
    monkeypatch.setenv("OSPREY_GRADING_GRADES", '{"scheme": "force-4x3"}')
    with pytest.raises(GradingSchemeUnknown, match="not a scheme"):
        GradingSettings.from_env()


def test_a_scheme_file_goes_with_the_copy_of_osprey_yaml(tmp_path: Path) -> None:
    """Every later `load_config` of the rendered copy (`harness.apply --reapply`'s) finds the file
    the setting names beside it."""
    from harness.render import load_config, write_config_copy

    source = tmp_path / "product"
    source.mkdir()
    (source / "grading-scheme.yaml").write_text(yaml.safe_dump(FORCE), encoding="utf-8")
    (source / "osprey.yaml").write_text("grading:\n  scheme: grading-scheme.yaml\n", "utf-8")
    out = tmp_path / "rendered"
    copy = write_config_copy(source / "osprey.yaml", out)
    assert load_config(copy).grading.resolved().model_dump() == FORCE


@pytest.mark.parametrize("grade", ["A$B", "A #", "A B", "'A'", ""])
def test_a_scheme_files_grade_is_safe_in_deployment_env(grade: str) -> None:
    with pytest.raises(ValueError, match="letters, digits or hyphens"):
        GradingSchemeAnswer(scheme="x-1", source=[grade], intelligence=["1"], handling=["H"])


def test_the_conduits_graph_never_offers_regrade_drawn() -> None:
    """Amendment 6 decision 7: the operator's command alone regrades; the Conduit's stamping
    graph, the one every route writes through, refuses the name, so no route can reach it."""
    from services.api.dataset_scope import stamping

    class Inner:
        async def regrade_drawn(self, *_: object) -> bool:
            raise AssertionError("reached")

    with pytest.raises(AttributeError, match="regrade_drawn"):
        stamping(Inner()).regrade_drawn  # type: ignore[arg-type]  # noqa: B018
