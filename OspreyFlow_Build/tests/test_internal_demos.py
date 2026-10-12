"""Code that exists only for an internal demo lives here, not in the product (`06_DECISIONS.md`
ADR-114 Amendment 2, the owner's ruling "Move Enron code to Build"): the product holds no Enron
reader, seed, registry entry or seed-runner row; the seed still runs from here through the product's
own runner, with this folder mounted read-only, and every real-data check applies unchanged.

What a mistake would do, and the case that catches it:
- the Enron code or entry put back in the product — `test_the_product_holds_no_internal_demo`;
- the seed run without this folder's code in its container, or as a synthetic seed —
  `test_the_enron_seed_runs_from_here_with_its_code_mounted_read_only`;
- the move losing the real-data check — `test_run_from_here_it_is_still_refused_without_its_exceptions_entry`;
- `--replace-links` reaching a seed that does not rewrite links —
  `test_replace_links_is_refused_for_a_seed_that_does_not_rewrite_them`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from internal_demos import seed as build_seed
from scripts import demo_registry, seed_internal

from tools.layout import ROOT

SUBS = {"osprey-demo-admin": "sub-admin", "osprey-demo-analyst": "sub-analyst"}


class _Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> str:
        self.calls.append(list(argv))
        return "Seeded.\n" if "run" in argv else ""


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    core = tmp_path / "OspreyFlow_Core"
    out = core / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("OSPREY_KEYCLOAK_PORT=8081\n", encoding="utf-8")
    (tmp_path / "OspreyFlow_Data" / "Enron_Mails" / "allen-p").mkdir(parents=True)
    return core


def _seed(checkout: Path, runner: _Runner, *, permitted: bool = True, **kwargs: object) -> list[str]:
    return seed_internal.seed_internal(
        "enron", checkout, run=runner, lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False, permitted=lambda name, use: permitted,
        datasets=build_seed.DATASETS_WITH_INTERNAL, code_mounts=build_seed.CODE_MOUNTS, **kwargs,
    )  # type: ignore[arg-type]  # fmt: skip


def test_the_product_holds_no_internal_demo() -> None:
    assert "enron" not in seed_internal.DATASETS
    assert "enron" not in {m.id for m in demo_registry.REGISTRY}
    assert demo_registry.internal_manifests() == ()
    committed = subprocess.run(["git", "ls-files", "OspreyFlow_Core"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.splitlines()  # fmt: skip
    assert not [f for f in committed if f.endswith(("/seed_enron.py", "demo_fixtures/enron.py"))]


def test_the_enron_seed_runs_from_here_with_its_code_mounted_read_only(checkout: Path) -> None:
    runner = _Runner()
    _seed(checkout, runner)
    (call,) = [c for c in runner.calls if "run" in c]
    here = Path(build_seed.__file__).resolve().parent
    assert f"{here}:/app/internal_demos:ro" in call
    assert call[call.index("-m") + 1] == "internal_demos.seed_enron"
    assert "--attested-permission" in call and "--attested-checkout" in call
    assert call[call.index("--case-name") + 1] == "Enron corpus (real data, this machine only)"


def test_run_from_here_it_is_still_refused_without_its_exceptions_entry(checkout: Path) -> None:
    runner = _Runner()
    with pytest.raises(seed_internal.SeedRefused, match="exceptions"):
        _seed(checkout, runner, permitted=False)
    assert runner.calls == [], "nothing is started"


def test_replace_links_is_refused_for_a_seed_that_does_not_rewrite_them(checkout: Path) -> None:
    runner = _Runner()
    _seed(checkout, runner, replace_links=True)
    assert any("--replace-links" in c for c in runner.calls)
    with pytest.raises(seed_internal.SeedRefused, match="--replace-links is not built for hmp"):
        seed_internal.seed_internal(
            "hmp", checkout, run=_Runner(), lookup_subs=lambda directory: SUBS,
            api_running=lambda compose: False, replace_links=True,
        )  # fmt: skip
