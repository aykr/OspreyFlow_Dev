"""The Enron corpus seeded from the product (ADR-114 Amendment 23, amending Amendment 2 and ADR-053):
an optional download each user makes and accepts, so its code is the product's; real data is still
admitted only by an acceptance on this machine or the owner's local exceptions entry, and only from a
checkout.

What a mistake would do, and the case that catches it:
- Enron left as an internal demo the product cannot offer — `test_the_product_offers_enron_as_a_download`;
- the seed run from the developer repository's code, or as a synthetic seed —
  `test_the_enron_seed_runs_the_products_code_as_real_data`;
- real data seeded with neither an acceptance nor an exceptions entry —
  `test_it_is_refused_without_an_acceptance_or_an_exceptions_entry`;
- an acceptance on this machine not admitting it — `test_an_acceptance_on_this_machine_admits_it`;
- `--replace-links` reaching a seed that does not rewrite links —
  `test_replace_links_is_refused_for_a_seed_that_does_not_rewrite_them`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from internal_demos.registry import INTERNAL
from scripts import demo_registry, real_data_acknowledgement, seed_internal

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
        api_running=lambda compose: False, permitted=lambda name, use: permitted, **kwargs,
    )  # type: ignore[arg-type]  # fmt: skip


def test_the_product_offers_enron_as_a_download() -> None:
    assert seed_internal.DATASETS["enron"].real_dataset == "enron"
    (manifest,) = [m for m in demo_registry.REGISTRY if m.id == "enron"]
    assert manifest.is_shipped and manifest.delivery == demo_registry.DELIVERY_DOWNLOAD
    assert INTERNAL == ()


def test_the_enron_seed_runs_the_products_code_as_real_data(checkout: Path) -> None:
    runner = _Runner()
    _seed(checkout, runner)
    (call,) = [c for c in runner.calls if "run" in c]
    assert call[call.index("-m") + 1] == "scripts.seed_enron"
    assert not any("internal_demos" in part for part in call)
    assert "--attested-permission" in call and "--attested-checkout" in call
    assert call[call.index("--case-name") + 1] == "Enron corpus (real data)"


def test_it_is_refused_without_an_acceptance_or_an_exceptions_entry(checkout: Path) -> None:
    runner = _Runner()
    with pytest.raises(seed_internal.SeedRefused, match="ospreyflow demo add enron"):
        _seed(checkout, runner, permitted=False)
    assert runner.calls == [], "nothing is started"


def test_an_acceptance_on_this_machine_admits_it(checkout: Path) -> None:
    corpus = checkout.parent / "OspreyFlow_Data" / "Enron_Mails"
    real_data_acknowledgement.record(corpus, "enron", source_file="enron_mail_20150507.tar.gz", sha256="0" * 64)
    runner = _Runner()
    _seed(checkout, runner, permitted=False)
    assert any("run" in c for c in runner.calls)


def test_replace_links_is_refused_for_a_seed_that_does_not_rewrite_them(checkout: Path) -> None:
    runner = _Runner()
    _seed(checkout, runner, replace_links=True)
    assert any("--replace-links" in c for c in runner.calls)
    with pytest.raises(seed_internal.SeedRefused, match="--replace-links is not built for hmp"):
        seed_internal.seed_internal(
            "hmp", checkout, run=_Runner(), lookup_subs=lambda directory: SUBS,
            api_running=lambda compose: False, replace_links=True,
        )  # fmt: skip
