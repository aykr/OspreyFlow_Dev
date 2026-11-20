"""A synthetic demo pack seeds from a user repository made by `git archive`, which has no `.git`
(`06_DECISIONS.md` ADR-114 Amendment 50, point 2; the checkout refusal itself is ADR-035 §C1 and
ADR-114 Amendment 2 decision 2, which group "the attested checkout" with the real-data checks).

The fault (N06): `seed_internal` refused with "this is not a checkout of the repository" before any
per-dataset branch, for every dataset, so no demo pack could be seeded on an install made from an
archive. Real and internal datasets keep the refusal, in its own words; `seed_paysim`'s own
`_is_checkout` looked only at the developer layout, the same fault in another shape.

Rule 12, which test fails if the fault returns:
- the refusal applied to a synthetic pack again (the whole check unconditional, as it was) —
  `test_a_synthetic_pack_seeds_without_a_git_folder_anywhere` (one case per synthetic pack, and it
  asserts the seed call is built and is told no checkout is attested);
- the refusal lifted for what must keep it (the exemption made too wide: the whole check removed, or
  keyed on something a real dataset also has) —
  `test_a_real_or_internal_dataset_is_still_refused_without_a_git_folder`;
- a new dataset added to `DATASETS` with no decision on whether it needs a checkout —
  `test_every_dataset_is_decided_either_way`;
- `seed_paysim` still refusing the user repository's layout, or no longer refusing a tree with no
  `.git` — `test_the_paysim_seed_recognises_both_layouts_and_a_bundle_is_still_not_one` (its
  download delivery's other checks are `tests/test_seed_paysim.py`'s and are not touched).
No Docker: the runner and the lookups are `test_seed_internal.py`'s own stand-ins.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import seed_enron, seed_internal, seed_paysim

from .test_seed_internal import Runner, _go, _seed_call

SYNTHETIC = [
    "hmp",
    "fixture-corp",
    "ledger",
    "prison-intelligence",
    "prison-intelligence-scale",
    "cyber-intrusion",
]
#: Datasets that read a data folder, or are real: the refusal stays (a paysim-like internal
#: dataset, the real Enron corpus, and a staged public dataset, which also reads a folder).
KEEPS_THE_CHECKOUT = ["paysim", "enron", "public"]

REFUSAL = "this is not a checkout of the repository"


@pytest.fixture
def git_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The user repository's layout as `user_repo` in `test_seed_internal.py` lays it out, but as
    `git archive` leaves it: no `.git` in it, and none in any folder above it."""
    monkeypatch.delenv("OSPREYFLOW_DEMO_DATA", raising=False)
    root = tmp_path / "ospreyflow"
    for folder in ("scripts", "harness"):
        (root / folder).mkdir(parents=True)
    (root / "osprey.yaml").write_text("profile: local-lite\n", encoding="utf-8")
    out = root / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("OSPREY_KEYCLOAK_PORT=8081\n", encoding="utf-8")
    above = [p for p in (root, *root.parents) if (p / ".git").exists()]
    assert above == [], f"this test needs a tree with no .git above it, but {above} has one"
    return root


@pytest.mark.parametrize("dataset", SYNTHETIC)
def test_a_synthetic_pack_seeds_without_a_git_folder_anywhere(
    git_archive: Path, dataset: str
) -> None:
    runner = Runner()
    _go(git_archive, runner, dataset=dataset)
    call = _seed_call(runner)
    assert call[call.index("-m") + 1] == seed_internal.DATASETS[dataset].script
    # No data folder is read, so nothing is attested: the container is not told a checkout was seen.
    assert "--attested-checkout" not in call


def _public_dataset(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = root.parent / "demo-data"
    (data / "public" / "some-open-data").mkdir(parents=True)
    (data / "public" / "some-open-data" / "dataset.yaml").write_text(
        "name: Some open data\ndomains: []\n", encoding="utf-8"
    )
    monkeypatch.setenv("OSPREYFLOW_DEMO_DATA", str(data))


@pytest.mark.parametrize("dataset", KEEPS_THE_CHECKOUT)
def test_a_real_or_internal_dataset_is_still_refused_without_a_git_folder(
    git_archive: Path, dataset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = Runner()
    extra: dict[str, object] = {}
    if dataset == "public":
        _public_dataset(git_archive, monkeypatch)
        extra["public_id"] = "some-open-data"
    # Every earlier check passes (the real-data exception is granted, a public data folder is
    # placed), so the checkout is the one thing that refuses; and nothing is started.
    with pytest.raises(seed_internal.SeedRefused) as refused:
        seed_internal.seed_internal(
            dataset,
            git_archive,
            run=runner,
            lookup_subs=lambda directory: {
                "osprey-demo-admin": "sub-admin-111",
                "osprey-demo-analyst": "sub-analyst-222",
            },
            api_running=lambda compose: False,
            permitted=lambda name, use: True,
            **extra,  # type: ignore[arg-type]
        )
    assert str(refused.value).startswith(REFUSAL)
    assert "never from a built bundle" in str(refused.value)
    assert runner.calls == []


def test_an_internal_dataset_with_a_git_folder_is_not_refused(
    git_archive: Path, tmp_path: Path
) -> None:
    """The refusal is about the checkout and nothing else: the same tree, with `.git`, seeds PaySim."""
    (git_archive / ".git").mkdir()
    (tmp_path / "OspreyFlow_Data" / "PaySIM_Dataset").mkdir(parents=True)
    runner = Runner()
    _go(git_archive, runner, dataset="paysim")
    assert "--attested-checkout" in _seed_call(runner)


def test_every_dataset_is_decided_either_way() -> None:
    """A dataset added later must be placed in one list here, which is a decision, not a default."""
    assert sorted(seed_internal.DATASETS) == sorted([*SYNTHETIC, *KEEPS_THE_CHECKOUT])


@pytest.mark.parametrize("module", [seed_paysim, seed_enron], ids=["paysim", "enron"])
def test_the_paysim_seed_recognises_both_layouts_and_a_bundle_is_still_not_one(
    module: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`seed_enron._is_checkout` is the model; `seed_paysim` looked only at the developer layout."""

    def in_tree(tree: Path, *below: str) -> bool:
        file = tree.joinpath(*below, "scripts", "seed_x.py")
        monkeypatch.setattr(module, "__file__", str(file))
        return module._is_checkout()  # type: ignore[attr-defined,no-any-return]

    user = tmp_path / "user"
    (user / ".git").mkdir(parents=True)
    assert in_tree(user)  # the product is the repository root

    developer = tmp_path / "developer"
    (developer / ".git").mkdir(parents=True)
    assert in_tree(developer, "OspreyFlow_Core")  # the product is one folder down

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    assert not in_tree(bundle)
    assert not in_tree(bundle, "OspreyFlow_Core")


def test_paysims_download_delivery_still_refuses_a_bundle() -> None:
    """Recognising the user repository does not loosen `resolve_source`'s refusal of a bundle."""
    with pytest.raises(seed_paysim.NotProvisionedError, match="checkout of the repository"):
        seed_paysim.resolve_source(Path("."), is_checkout=False)
