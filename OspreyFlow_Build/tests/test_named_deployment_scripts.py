"""The checkout's scripts that find the deployment themselves (`scripts.refresh`, the seeds) reach
the one `ospreyflow --name` chose (ADR-138 decision 2), through `OSPREYFLOW_DEPLOYMENT_DIR`.

- `start --build` or `demo add` rebuilding or seeding the checkout's deployment when another was
  named — `test_the_named_folder_is_the_one_refresh_and_the_seeds_use`;
- a named deployment rebuilt from three folders above the home folder —
  `test_refresh_builds_a_named_deployment_from_its_own_build_context`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from scripts import refresh, seed_internal


def _deployment(folder: Path, context: str = "../../..") -> Path:
    folder.mkdir(parents=True)
    (folder / "compose.yaml").write_text(
        yaml.safe_dump({"name": folder.name, "services": {"api": {"build": {"context": context}}}}),
        encoding="utf-8",
    )
    (folder / "deployment.env").write_text("X=1\n", encoding="utf-8")
    return folder


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    core = tmp_path / "OspreyFlow_Core"
    (core / "scripts").mkdir(parents=True)
    (core / "osprey.yaml").write_text("profile: local-lite\n", encoding="utf-8")
    _deployment(core / "deploy" / "generated" / "local-lite")
    return core


def test_the_named_folder_is_the_one_refresh_and_the_seeds_use(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = _deployment(tmp_path / "home" / ".ospreyflow" / "deployments" / "alpha", str(checkout))
    assert refresh._deployment_dir(checkout) == checkout / "deploy" / "generated" / "local-lite"
    monkeypatch.setenv(refresh.DEPLOYMENT_DIR_VARIABLE, str(named))
    assert refresh._deployment_dir(checkout) == named
    calls: list[list[str]] = []
    seed_internal.seed_internal(
        "hmp", checkout, run=lambda argv: calls.append(list(argv)) or "",
        lookup_subs=lambda directory: {"osprey-demo-admin": "a", "osprey-demo-analyst": "b"},
        api_running=lambda compose: False,
    )  # fmt: skip
    (seed,) = [c for c in calls if "run" in c]
    assert str(named / "compose.yaml") in seed
    assert not any("local-lite" in word for word in seed)


def test_a_named_folder_with_nothing_rendered_is_refused_in_words(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(refresh.DEPLOYMENT_DIR_VARIABLE, str(tmp_path / "nowhere"))
    with pytest.raises(refresh.NothingToRefresh, match="ospreyflow install --name"):
        refresh._deployment_dir(checkout)


def test_refresh_builds_a_named_deployment_from_its_own_build_context(
    checkout: Path, tmp_path: Path
) -> None:
    from harness.render import load_config

    named = _deployment(tmp_path / "deployments" / "alpha", str(checkout))
    services = yaml.safe_load((named / "compose.yaml").read_text(encoding="utf-8"))["services"]
    config = refresh._like_the_deployment(load_config(tmp_path / "none.yaml"), services, named)
    assert config.components.source_path == str(checkout.resolve())
