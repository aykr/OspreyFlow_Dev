"""R1's install on kind renders the candidate's own runbook and Terraform, never a kept older
render's (the orchestrator's review of platform-b's step-6 run sheet, 14 November 2026).

R1 keeps the install's render outside the copy (`r1_kind.KEPT`), because each sync to the server
prunes the render folder. An upgrade is an install of a newer candidate over a deployment whose
render is kept. Before this fix, `runbook("INSTALL")` put the kept render back first, then rendered
nothing because an INSTALL.md was there. So the candidate's install ran v0.5.1's runbook, and
install step 2's Terraform stand-in read v0.5.1's `.tf`: the candidate's new Secrets were never
made.

What a mistake would do, and the case that catches it (rule 12):
- an older kept render used for a newer candidate:
  `test_an_upgrade_runs_the_candidate_s_own_runbook_and_terraform`;
- a resumed install of the same release losing what its earlier blocks pinned (the images pushed):
  `test_an_install_resumed_keeps_its_own_render`.

Each runs `r1_kind.runbook("INSTALL", 1)` itself, with the shell and the cluster stood in for.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

GATES = Path(__file__).parents[1] / "process/lanes/platform/gates"

CANDIDATE = {
    "values.yaml": "release: candidate\n",
    "INSTALL.md": "# Install\n\n## 1. Settings\n\n```bash\necho candidate-install\n```\n",
    "terraform/secrets.tf": 'resource "kubernetes_secret" "candidate_new" {}\n',
    "images.yaml": "images: unpinned\n",
}


def _r1_kind():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(GATES))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(GATES))
    return r1_kind


def _write(folder: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text)


class _Done:
    """`subprocess.Popen` of the runbook's script: it ran, and said nothing."""

    def __init__(self, args: list[str], **_: Any) -> None:
        self.stdout = iter(())
        _Done.scripts.append(Path(args[1]).read_text())

    def wait(self) -> int:
        return 0

    scripts: list[str] = []


@pytest.fixture
def r1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """r1_kind with its folders in tmp_path; the render writes the candidate's files, as the
    candidate's `python -m harness.render` would; the folder starts pruned, as after a sync."""
    r1_kind = _r1_kind()
    state = tmp_path / "state"
    monkeypatch.setattr(r1_kind, "STATE", state)
    monkeypatch.setattr(r1_kind, "RECORDS", state / "records")
    monkeypatch.setattr(r1_kind, "FOLDER", tmp_path / "core/deploy/generated/cloud-platform")
    monkeypatch.setattr(r1_kind, "KEPT", state / "render")
    renders: list[tuple[str, ...]] = []

    def sh(*args: str, **_: Any) -> str:
        if "harness.render" in args:
            renders.append(args)
            _write(r1_kind.FOLDER, CANDIDATE)
        return "172.18.0.2" if args[:2] == ("docker", "inspect") else ""

    monkeypatch.setattr(r1_kind, "sh", sh)
    monkeypatch.setattr(r1_kind, "kubectl", lambda *a, **k: "")
    monkeypatch.setattr(r1_kind, "ca", lambda: tmp_path / "ca")
    monkeypatch.setattr(r1_kind.subprocess, "Popen", _Done)
    _Done.scripts = []
    r1_kind.renders = renders  # type: ignore[attr-defined]
    return r1_kind


def test_an_upgrade_runs_the_candidate_s_own_runbook_and_terraform(r1) -> None:  # type: ignore[no-untyped-def]
    _write(r1.KEPT, {
        "values.yaml": "release: v0.5.1\n",
        "INSTALL.md": "# Install\n\n## 1. Settings\n\n```bash\necho v051-install\n```\n",
        "terraform/secrets.tf": 'resource "kubernetes_secret" "v051" {}\n',
        "terraform/gone.tf": "# a file the candidate no longer renders\n",
        "images.yaml": "images: pinned for v0.5.1\n",
    })  # fmt: skip
    r1.runbook("INSTALL", 1)
    assert r1.renders, "the candidate's own render"
    [script] = _Done.scripts
    assert "echo candidate-install" in script and "v051" not in script
    # Install step 2's Terraform stand-in reads the folder: the candidate's files alone.
    assert sorted(p.name for p in (r1.FOLDER / "terraform").glob("*.tf")) == ["secrets.tf"]
    assert "candidate_new" in (r1.FOLDER / "terraform/secrets.tf").read_text()
    assert (r1.FOLDER / "images.yaml").read_text() == CANDIDATE["images.yaml"]
    # The candidate's render is kept now; the older one is set aside, not lost.
    assert (r1.KEPT / "values.yaml").read_text() == CANDIDATE["values.yaml"]
    before = r1.STATE / "render.before-upgrade"
    assert (before / "values.yaml").read_text() == "release: v0.5.1\n"


def test_an_install_resumed_keeps_its_own_render(r1) -> None:  # type: ignore[no-untyped-def]
    """The same release, resumed after a sync: its runbook and Terraform are the candidate's own, so
    what its earlier blocks left in the render (the images pushed and pinned) is put back."""
    _write(r1.KEPT, {**CANDIDATE, "images.yaml": "images: pinned at step 3\n"})
    r1.runbook("INSTALL", 4)
    assert (r1.FOLDER / "images.yaml").read_text() == "images: pinned at step 3\n"
    assert not (r1.STATE / "render.before-upgrade").exists()


def test_a_first_install_renders_its_own(r1) -> None:  # type: ignore[no-untyped-def]
    r1.runbook("INSTALL", 1)
    [script] = _Done.scripts
    assert "echo candidate-install" in script
    assert (r1.KEPT / "INSTALL.md").read_text() == CANDIDATE["INSTALL.md"]
