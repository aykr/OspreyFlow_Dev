"""The PID naming gate (Brief 1, stage 6), shown able to fail and then clean on the real tree.

The two banned words are built from pieces below, so that this file, which is itself a PID-named
file the gate scans, does not hold them. Each plant takes the shape the real thing has: a name in a
tuple of the real `pid_names.py`, a real PID file's name, a line of a real generated CSV, the
recipe layout of the repository's recipes (id, label, handling originator and unit), the registered
dataset's fields, and the generator's own `created_by` and node-id functions.

Pure: no store, no network; it generates the demo plan in memory, a few seconds.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from pathlib import Path

import pytest
from tools import pid_naming_check as gate

from demo_fixtures import pid_files, pid_plan, pid_writes
from demo_fixtures.datasets import PID, SeedDataset

BANNED = "h" + "mp"
OTHER = "holly" + "wood"
ROOT = gate.repository_root()
CORE = ROOT / "OspreyFlow_Core"


@pytest.fixture(scope="module")
def plan() -> pid_plan.Plan:
    return pid_plan.build_plan("demo")


def _tree(tmp_path: Path) -> Path:
    """A repository-shaped folder holding copies of two real PID files."""
    for relative in ("packages/demo_fixtures/pid_names.py", "scripts/write_pid_files.py"):
        destination = tmp_path / "OspreyFlow_Core" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(CORE / relative, destination)
    (tmp_path / "OspreyFlow_Build").mkdir()
    return tmp_path


# --- what it finds, and that it finds something --------------------------------------------------


def test_the_pid_files_are_found_by_name_and_include_the_known_ones() -> None:
    found = {str(p.relative_to(ROOT)) for p in gate.pid_files(ROOT)}
    assert {
        "OspreyFlow_Core/packages/demo_fixtures/pid_plan.py",
        "OspreyFlow_Core/packages/demo_fixtures/pid_files.py",
        "OspreyFlow_Core/scripts/write_pid_files.py",
        "OspreyFlow_Build/tests/scenarios/test_pid_plan.py",
        "OspreyFlow_Build/tests/services/api/test_pid_access_control.py",
    } <= found
    assert not [f for f in found if "Rapid" in f], "a word, not a substring of another word"


def test_a_check_over_nothing_is_refused(tmp_path: Path) -> None:
    (tmp_path / "OspreyFlow_Core").mkdir()
    with pytest.raises(gate.NothingToCheck):
        gate.check(tmp_path, generated=False)


def test_the_registered_pid_datasets_are_found() -> None:
    assert {d.id for d in gate.pid_datasets()} == {
        "prison-intelligence",
        "prison-intelligence-scale",
    }


# --- red: each plant is reported ----------------------------------------------------------------


def test_a_word_in_a_pid_files_contents_is_reported_with_its_line(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    target = root / "OspreyFlow_Core/packages/demo_fixtures/pid_names.py"
    text = target.read_text()
    assert '    "Alderdale",\n' in text
    target.write_text(text.replace('    "Alderdale",\n', f'    "Alder{BANNED}dale",\n', 1))

    hits = gate.check(root, generated=False)

    assert len(hits) == 1
    assert hits[0].where.startswith("OspreyFlow_Core/packages/demo_fixtures/pid_names.py:")
    assert BANNED in hits[0].text.lower()


def test_the_other_word_is_reported_whatever_its_case(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    target = root / "OspreyFlow_Core/scripts/write_pid_files.py"
    target.write_text(target.read_text() + f"\n# the {OTHER.upper()} wing\n")
    hits = gate.check(root, generated=False)
    assert [h.where.split(":")[0] for h in hits] == ["OspreyFlow_Core/scripts/write_pid_files.py"]


def test_a_word_in_a_pid_files_name_is_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / f"OspreyFlow_Core/packages/demo_fixtures/pid_{BANNED}_extra.py").write_text("X = 1\n")
    hits = gate.check(root, generated=False)
    assert [h.where for h in hits] == [
        f"file name OspreyFlow_Core/packages/demo_fixtures/pid_{BANNED}_extra.py"
    ]


def test_a_word_in_a_recipe_id_and_its_originator_is_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    recipe = root / "OspreyFlow_Core/packages/demo_fixtures/pid_pin_calls_recipe.yaml"
    recipe.write_text(
        f'id: pid-{BANNED}-calls\nversion: 1\nlabel: "PID calls"\n'
        "connector:\n  profile: pid-generic\n"
        f"defaults:\n  handling: {{classification: OFFICIAL, handling_code: P, "
        f"originator: pid-{OTHER}, owning_unit: pid-unit}}\n"
    )
    hits = gate.check(root, generated=False)
    recipe_hits = {h.where for h in hits if h.where.startswith("recipe ")}
    assert recipe_hits == {
        f"recipe pid-{BANNED}-calls['id']",
        f"recipe pid-{BANNED}-calls['defaults']['handling']['originator']",
    }
    # And the same words, found in the file's contents by the file scan.
    assert {h.where for h in hits if not h.where.startswith("recipe ")} == {
        "OspreyFlow_Core/packages/demo_fixtures/pid_pin_calls_recipe.yaml:1",
        "OspreyFlow_Core/packages/demo_fixtures/pid_pin_calls_recipe.yaml:7",
    }


def test_a_word_in_a_registered_dataset_is_reported() -> None:
    planted = SeedDataset(
        id=f"prison-intelligence-{BANNED}",
        name=PID.name,
        source=PID.source,
        case_name=f"The {OTHER} case",
        domains=PID.domains,
    )
    hits = gate.scan_registry([planted])
    assert {h.where for h in hits} == {
        f"registered dataset prison-intelligence-{BANNED}.id",
        f"registered dataset prison-intelligence-{BANNED}.case_name",
    }


def test_a_word_in_a_generated_id_and_in_the_generators_own_name_is_reported(
    plan: pid_plan.Plan, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_node_id = pid_writes.node_id
    monkeypatch.setattr(pid_writes, "node_id", lambda key: real_node_id(key) + f"-{BANNED}")
    monkeypatch.setattr(pid_writes, "CREATED_BY", f"pid-{BANNED}-generator")

    hits = gate.scan_writes(plan)

    assert any(h.where.startswith("generated node ") and BANNED in h.where for h in hits)
    assert any(h.where.startswith("generated link ") for h in hits)
    assert any("created_by" in h.text for h in hits)


def test_a_word_in_the_plans_report_text_is_reported(plan: pid_plan.Plan) -> None:
    key = next(iter(plan.report_texts))
    texts = dict(plan.report_texts)
    texts[key] += f" Seen on the {BANNED} landing."
    planted = dataclasses.replace(plan, report_texts=texts)
    assert any("report_texts" in h.where for h in gate.scan_plan(planted))


def test_a_word_in_a_line_of_a_generated_file_is_reported(plan: pid_plan.Plan) -> None:
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder)
        pid_files.write_files(plan, out)
        assert gate.scan_generated_files(out) == [], "the real output is clean"
        target = out / pid_files.ESTATE
        lines = target.read_text().splitlines(keepends=True)
        lines[3] = lines[3].replace(",", f",{BANNED} ", 1)
        target.write_text("".join(lines))

        hits = gate.scan_generated_files(out)

    assert [h.where for h in hits] == [f"generated file {pid_files.ESTATE}:4"]


def test_a_word_in_a_generated_file_name_is_reported(plan: pid_plan.Plan) -> None:
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder)
        (out / "pictures").mkdir()
        (out / "pictures" / f"{BANNED}_yard.png").write_bytes(b"\x89PNG")
        hits = gate.scan_generated_files(out)
    assert [h.where for h in hits] == [f"generated file name pictures/{BANNED}_yard.png"]


def test_a_picture_s_bytes_are_not_scanned_for_the_words(tmp_path: Path) -> None:
    """Pixel data could spell them by chance, which would be a false alarm no one could fix."""
    root = _tree(tmp_path)
    (root / "OspreyFlow_Core/packages/demo_fixtures/pid_picture.png").write_bytes(
        BANNED.encode() + b"\xff\xfe"
    )
    assert gate.check(root, generated=False) == []


# --- green: the real tree ------------------------------------------------------------------------


def test_the_real_tree_and_its_generated_output_are_clean(plan: pid_plan.Plan) -> None:
    assert gate.check(ROOT, plan=plan) == []


def test_the_check_prints_every_hit_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path)
    (root / f"OspreyFlow_Core/packages/demo_fixtures/pid_{BANNED}.py").write_text("")
    monkeypatch.setattr(gate, "repository_root", lambda: root)
    monkeypatch.setattr(gate, "pid_datasets", lambda: [PID])
    monkeypatch.setattr(gate, "scan_generated", lambda *a, **k: [])
    assert gate.main([]) == 1
    assert "file name" in capsys.readouterr().out
