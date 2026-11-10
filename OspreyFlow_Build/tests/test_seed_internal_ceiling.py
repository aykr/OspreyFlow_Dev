"""ADR-148 decision 10 for the demo packs (L1.10, the orchestrator's (b)): a pack whose data is
marked above the deployment's highest marking is refused before its seed starts, so a pack written
in several transactions (fixture-corp's SECRET shortcut, by design) is never partly written. A pack
declares its highest marking only where a test below proves every write it makes is within it; one
that declares none is judged as the scheme's highest, so the refusal fails closed."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import seed_internal
from scripts.seed_internal import DATASETS, SeedRefused

from ontology.handling import load_uk_le_scheme

from .test_seed_internal import SUBS, Runner

SCHEME = load_uk_le_scheme()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout as `test_seed_internal`'s own: `.git`, a rendered local-lite deployment."""
    (tmp_path / ".git").mkdir()
    core = tmp_path / "OspreyFlow_Core"
    out = core / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("OSPREY_KEYCLOAK_PORT=8081\n", encoding="utf-8")
    (core / "scripts").mkdir()
    (tmp_path / "OspreyFlow_Data" / "PaySIM_Dataset").mkdir(parents=True)
    return core


def _render(repo: Path, ceiling: str | None) -> None:
    env = repo / "deploy" / "generated" / "local-lite" / "deployment.env"
    line = f"OSPREY_HIGHEST_MARKING={ceiling}\n" if ceiling is not None else ""
    env.write_text("OSPREY_KEYCLOAK_PORT=8081\n" + line, encoding="utf-8")


def _seed(repo: Path, dataset: str, runner: Runner) -> list[str]:
    return seed_internal.seed_internal(
        dataset, repo, run=runner, lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False, permitted=lambda name, use: True,
    )  # fmt: skip


def test_a_pack_above_the_ceiling_is_refused_before_its_seed_starts(repo: Path) -> None:
    _render(repo, "OFFICIAL-SENSITIVE")
    runner = Runner()
    with pytest.raises(SeedRefused) as raised:
        _seed(repo, "fixture-corp", runner)
    words = str(raised.value)
    assert "OFFICIAL-SENSITIVE" in words and "fixture-corp" in words
    assert runner.calls == [], "something ran before the refusal"


def test_a_pack_within_the_ceiling_is_seeded(repo: Path) -> None:
    _render(repo, "OFFICIAL-SENSITIVE")
    runner = Runner()
    _seed(repo, "cyber-intrusion", runner)
    assert any("scripts.seed_cyber_intrusion" in call for call in runner.calls)


def test_with_no_ceiling_rendered_every_pack_is_seeded_as_before(repo: Path) -> None:
    _render(repo, None)
    runner = Runner()
    _seed(repo, "fixture-corp", runner)
    assert any("scripts.seed_fixture_corp" in call for call in runner.calls)


def test_a_pack_that_declares_nothing_is_judged_as_the_scheme_s_highest(repo: Path) -> None:
    """Fails closed: an undeclared pack is refused under any ceiling below the scheme's top."""
    undeclared = [name for name, spec in DATASETS.items() if spec.highest_marking is None]
    assert "fixture-corp" in undeclared
    _render(repo, "OFFICIAL-SENSITIVE")
    for name in undeclared:
        if name in ("public", "enron"):  # these need their own arguments or data first
            continue
        with pytest.raises(SeedRefused):
            _seed(repo, name, Runner())


def test_cyber_intrusions_declaration_holds_for_every_write() -> None:
    from scripts.seed_cyber_intrusion import edge_writes, node_writes

    declared = DATASETS["cyber-intrusion"].highest_marking
    assert declared is not None
    top = SCHEME.classification.index(declared)
    writes = [*node_writes("load-1"), *edge_writes("load-1")]
    assert writes
    assert all(SCHEME.classification.index(w.handling.classification) <= top for w in writes)


def test_paysims_declaration_holds_for_every_write() -> None:
    """Every PaySim write takes the seed's one marking: `build_graph_writes` stamps each node and
    link with the handling it is given (proved over synthetic rows), and the seed gives it
    `_HANDLING`, within the declaration."""
    from scripts import seed_paysim

    from demo_fixtures.paysim import PaysimRow, build_graph_writes
    from schemas.domain import Handling

    declared = DATASETS["paysim"].highest_marking
    assert declared is not None
    marking = seed_paysim._HANDLING.classification
    assert SCHEME.classification.index(marking) <= SCHEME.classification.index(declared)
    probe = Handling(
        classification="PUBLIC", handling_code="P", originator="probe", owning_unit="probe"
    )
    rows = [
        PaysimRow(index=i, step=1, type="TRANSFER", amount=9.5, origin=f"C{i}",
                  destination=f"C{i + 1}", is_fraud=1, is_flagged=0)
        for i in range(3)
    ]  # fmt: skip
    nodes, edges = build_graph_writes(rows, created_by="seed", handling=probe)
    assert nodes and edges
    assert all(w.handling == probe for w in [*nodes, *edges]), "a write at another marking"
