"""`06_DECISIONS.md` ADR-035 §C2's packaging gate — named prospectively there, built here against
`scripts/packaging_gate.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import packaging_gate
from scripts.demo_registry import DemoManifest


def test_reclassifying_an_internal_demo_as_shipped_fails_if_its_data_remains() -> None:
    """The mistake this test names: someone flips a demo's own registry entry from `internal` to
    `shipped` — perhaps believing the data has been cleared for release — while its dataset still
    physically lives under `demo-data/`, ADR-035 §C1's own fixed provisioning location for exactly
    the internal-only case. The gate must not trust the registry's own (now wrong) classification
    for this path: `demo-data/` is checked independently of any registry entry's `distribution`
    field, so the artefact is still refused."""
    reclassified = DemoManifest(
        id="misclassified-demo",
        distribution="shipped",  # the mistake: flipped, but the data was not moved or removed
        seed_module="scripts.seed_misclassified_demo",
        paths=("demo-data/misclassified-demo/data.csv",),
    )

    violations = packaging_gate.find_internal_demo_data(
        ["demo-data/misclassified-demo/data.csv"], registry=(reclassified,)
    )

    assert violations == ["demo-data/misclassified-demo/data.csv"]


def test_removing_the_exclusion_step_itself_fails_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CLAUDE.md` rule 15's own discipline: a gate that only ever proves the current, correct
    state passes is not proof it would catch its own removal. Neuters the always-internal marker
    list `find_internal_demo_data` checks independently of the registry — the same mechanism the
    test above depends on — and confirms the identical fixture that test proves is caught now
    slips through, so the mechanism under test is real, not vacuous."""
    monkeypatch.setattr(packaging_gate, "_ALWAYS_INTERNAL_MARKERS", ())

    violations = packaging_gate.find_internal_demo_data(
        ["demo-data/misclassified-demo/data.csv"], registry=()
    )

    assert violations == [], (
        "removing _ALWAYS_INTERNAL_MARKERS should make this check blind to the same path the "
        "test above proves it catches — if this assertion fails, the check above may be passing "
        "for a reason unrelated to the mechanism it claims to test"
    )


def test_a_real_internal_registry_entrys_own_path_is_caught_without_the_fixed_marker() -> None:
    """The registry-driven half, independent of the fixed-path half the two tests above cover:
    a demo correctly classified `internal`, whose data lives somewhere other than `demo-data/`,
    is still caught via its own registry entry."""
    internal_demo = DemoManifest(
        id="enron",
        distribution="internal",
        seed_module="scripts.seed_enron_fixture",
        paths=("tests/scenarios/fixtures/enron.py",),
    )

    violations = packaging_gate.find_internal_demo_data(
        ["tests/scenarios/fixtures/enron.py", "tests/scenarios/fixtures/hmp.py"],
        registry=(internal_demo,),
    )

    assert violations == ["tests/scenarios/fixtures/enron.py"]


def test_real_data_exceptions_file_is_always_refused_regardless_of_registry() -> None:
    """ADR-035 §C1/§C2: `config/real_data_exceptions.yaml` never enters an artefact — a fixed
    refusal that does not depend on any registry entry naming it."""
    violations = packaging_gate.find_internal_demo_data(
        ["config/real_data_exceptions.yaml", "config/real_data_exceptions.example.yaml"],
        registry=(),
    )

    assert violations == ["config/real_data_exceptions.yaml"]


def test_the_real_registry_produces_no_violations_for_a_clean_artefact() -> None:
    """The positive case: an artefact containing only the real, shipped demo fixtures' own paths
    produces nothing to refuse."""
    from scripts.demo_registry import REGISTRY

    clean_paths = [
        "tests/scenarios/fixtures/hmp.py",
        "tests/scenarios/fixtures/hmp_graph.py",
        "tests/scenarios/fixtures/fixture_corp.py",
    ]
    assert packaging_gate.find_internal_demo_data(clean_paths, registry=REGISTRY) == []


# --- ADR-034 §B7 #1: no private-tree file in the artefact ---------------------------------------


def test_a_private_tree_file_in_the_artefact_fails_the_gate() -> None:
    violations = packaging_gate.find_private_tree_files(
        ["process/07_BUILD_PLAN.md", "spec/00_ARCHITECTURE.md", ".claude/CLAUDE.md"]
    )
    assert set(violations) == {"process/07_BUILD_PLAN.md", ".claude/CLAUDE.md"}


def test_no_private_tree_file_in_a_clean_artefact_passes() -> None:
    clean = ["spec/00_ARCHITECTURE.md", "packages/schemas/domain.py", "README.md"]
    assert packaging_gate.find_private_tree_files(clean) == []


# --- ADR-034 §B7 #2: no authorship identifier in the artefact --------------------------------


def test_an_authorship_identifier_in_build_metadata_fails_the_gate() -> None:
    violations = packaging_gate.find_authorship_identifiers(
        {
            "image.label:org.opencontainers.image.authors": "Ayan Kar <ayan.kar@solirius.com>",
            "image.label:org.opencontainers.image.vendor": "OspreyFlow",
        }
    )
    assert len(violations) == 1
    assert "org.opencontainers.image.authors" in violations[0]


def test_no_authorship_identifier_in_clean_metadata_passes() -> None:
    assert (
        packaging_gate.find_authorship_identifiers(
            {"image.label:org.opencontainers.image.vendor": "OspreyFlow"}
        )
        == []
    )


# --- Reading a real artefact's own file list -----------------------------------------------------


def test_tarball_members_reads_a_real_tar_files_own_member_names(tmp_path: Path) -> None:
    import tarfile

    tar_path = tmp_path / "bundle.tar.gz"
    inner = tmp_path / "LICENSE"
    inner.write_text("Apache License")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(inner, arcname="LICENSE")

    assert packaging_gate.tarball_members(tar_path) == ["LICENSE"]


def test_docker_save_layer_paths_reads_the_union_across_every_layer_not_only_the_final_view(
    tmp_path: Path,
) -> None:
    """A fabricated `docker save`-shaped tarball: two layer tars, `manifest.json` naming both.
    The file added in layer 1 must be found even though it is absent from layer 2 — the whole
    point of reading every layer rather than only the last one (this module's own docstring)."""
    import tarfile

    layer1_dir = tmp_path / "layer1"
    layer1_dir.mkdir()
    (layer1_dir / "secret.txt").write_text("process/07_BUILD_PLAN.md was here")
    layer1_tar = tmp_path / "layer1.tar"
    with tarfile.open(layer1_tar, "w") as tar:
        tar.add(layer1_dir / "secret.txt", arcname="secret.txt")

    layer2_dir = tmp_path / "layer2"
    layer2_dir.mkdir()
    (layer2_dir / "app.py").write_text("print('hello')")
    layer2_tar = tmp_path / "layer2.tar"
    with tarfile.open(layer2_tar, "w") as tar:
        tar.add(layer2_dir / "app.py", arcname="app.py")

    manifest = [{"Layers": ["layer1.tar", "layer2.tar"]}]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(__import__("json").dumps(manifest))

    save_tar = tmp_path / "image-save.tar"
    with tarfile.open(save_tar, "w") as outer:
        outer.add(manifest_path, arcname="manifest.json")
        outer.add(layer1_tar, arcname="layer1.tar")
        outer.add(layer2_tar, arcname="layer2.tar")

    paths = packaging_gate.docker_save_layer_paths(save_tar)

    assert paths == {"secret.txt", "app.py"}


def test_check_artefact_aggregates_every_finding_and_is_empty_when_clean() -> None:
    dirty = packaging_gate.check_artefact(
        ["process/07_BUILD_PLAN.md", "demo-data/x/data.csv"],
        text_blobs={"label": "Ayan Kar <ayan.kar@solirius.com>"},
    )
    assert set(dirty) == {"private_tree_files", "internal_demo_data", "authorship_identifiers"}

    clean = packaging_gate.check_artefact(
        ["spec/00_ARCHITECTURE.md", "tests/scenarios/fixtures/hmp.py"],
        text_blobs={"label": "OspreyFlow"},
    )
    assert clean == {}


# --- ADR-034 §B2/§B6 addendum: LICENSE/NOTICE presence and content --------------------------------


def test_license_and_notice_absent_fails_the_gate() -> None:
    violations = packaging_gate.check_license_and_notice(None, None)
    assert "LICENSE is missing" in violations
    assert "NOTICE is missing" in violations


def test_license_not_matching_the_reference_fails_the_gate() -> None:
    violations = packaging_gate.check_license_and_notice("not the real licence text", "x")
    assert any("LICENSE" in v for v in violations)


def test_notice_missing_the_holder_name_fails_the_gate() -> None:
    violations = packaging_gate.check_license_and_notice(
        packaging_gate.APACHE_2_0_LICENSE_REFERENCE_PATH.read_text(encoding="utf-8"),
        "Copyright 2026 Some Other Entity",
    )
    assert violations == ["NOTICE does not name 'The OspreyFlow Authors'"]


def test_the_real_committed_license_and_notice_pass() -> None:
    """The positive case, against the real, committed files this session created."""
    from scripts.packaging_gate import REPO_ROOT

    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    notice_text = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")

    assert packaging_gate.check_license_and_notice(license_text, notice_text) == []
