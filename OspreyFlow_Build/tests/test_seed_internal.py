"""Loading an internal demo dataset into the running deployment, in one command.

Seen: the PaySim seed was written to run on the owner's Mac, where it would have written a DuckDB
file the deployment never reads (the deployment's analytics store lives in a Docker volume) and
where nothing made the case or shared it with the demo accounts. `scripts/seed_internal.py` runs the
seed in a one-shot container from the Conduit's own image, inside the deployment's network, as
`harness.apply` runs its own seeds, with the checkout's `scripts/` and the data folder mounted
read-only. The Conduit must be stopped while it runs (DuckDB's exclusive lock), and is started again
after, whether the seed worked or not. No Docker here: the runner and the lookups are injected, and
each test names what it would catch.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts import seed_internal

ADMIN = "osprey-demo-admin"
ANALYST = "osprey-demo-analyst"
SUBS = {ADMIN: "sub-admin-111", ANALYST: "sub-analyst-222"}


class Runner:
    def __init__(self, fail_seed: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail_seed = fail_seed

    def __call__(self, argv: Sequence[str]) -> str:
        self.calls.append(list(argv))
        if self.fail_seed and "run" in argv:
            raise seed_internal.SeedFailed("the seed exited 1")
        return "Seeded 70,000 accounts.\n" if "run" in argv else ""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout: `OspreyFlow_Core` inside a folder with `.git`, `OspreyFlow_Data` beside it."""
    root = tmp_path
    (root / ".git").mkdir()
    core = root / "OspreyFlow_Core"
    out = core / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("OSPREY_KEYCLOAK_PORT=8081\n", encoding="utf-8")
    (core / "scripts").mkdir()
    (root / "OspreyFlow_Data" / "PaySIM_Dataset").mkdir(parents=True)
    return core


def _go(
    repo: Path,
    runner: Runner,
    *,
    api_running: bool = False,
    stop_api: bool = False,
    subs: dict[str, str] | None = None,
) -> list[str]:
    return seed_internal.seed_internal(
        "paysim",
        repo,
        run=runner,
        lookup_subs=lambda directory: SUBS if subs is None else subs,
        api_running=lambda compose: api_running,
        stop_api=stop_api,
    )


def _seed_call(runner: Runner) -> list[str]:
    (call,) = [c for c in runner.calls if "run" in c]
    return call


def test_the_seed_runs_in_the_conduits_image_inside_the_deployment_not_on_the_host(
    repo: Path,
) -> None:
    """Catches the original fault: a host-side seed writes where the deployment does not read."""
    runner = Runner()
    _go(repo, runner)
    call = _seed_call(runner)
    out = repo / "deploy" / "generated" / "local-lite"
    assert call[:2] == ["docker", "compose"]
    assert call[call.index("--env-file") + 1] == str(out / "deployment.env")
    assert ["run", "--rm", "--no-deps"] == call[call.index("run") : call.index("run") + 3]
    assert call[call.index("--entrypoint") + 1] == "python"
    assert "api" in call
    assert call[call.index("-m") + 1] == "scripts.seed_paysim"


def test_scripts_and_data_are_mounted_read_only(repo: Path) -> None:
    """Catches a seed that could change the checkout or the dataset."""
    call = _seed_call(_run_and_return(repo))
    mounts = [call[i + 1] for i, a in enumerate(call) if a == "-v"]
    assert f"{repo}/scripts:/app/scripts:ro" in mounts
    assert f"{repo.parent}/OspreyFlow_Data:/internal-data:ro" in mounts
    assert all(m.endswith(":ro") for m in mounts)


def _run_and_return(repo: Path, **kwargs: object) -> Runner:
    runner = Runner()
    _go(repo, runner, **kwargs)  # type: ignore[arg-type]
    return runner


def test_the_demo_admin_is_an_author_and_the_demo_analyst_an_editor_by_subject(
    repo: Path,
) -> None:
    """The grants are written to the identity provider's subjects, the Conduit's principal ids, and
    to nothing else: a name would never match a token."""
    call = _seed_call(_run_and_return(repo))
    grants = [call[i + 1] for i, a in enumerate(call) if a == "--grant"]
    assert sorted(grants) == ["sub-admin-111=author", "sub-analyst-222=editor"]
    assert call[call.index("--case-name") + 1] == "PaySim mobile money (internal)"
    assert "--attested-checkout" in call


def test_it_refuses_when_the_conduit_is_running_and_says_which_flag_to_use(repo: Path) -> None:
    """DuckDB's exclusive lock: seeding into a running Conduit fails, and stopping it for you is a
    data-affecting decision (`harness.apply`'s own rule)."""
    runner = Runner()
    with pytest.raises(seed_internal.SeedRefused, match="--stop-api"):
        _go(repo, runner, api_running=True)
    assert runner.calls == []


def test_with_stop_api_it_stops_seeds_then_starts_the_conduit_again(repo: Path) -> None:
    runner = Runner()
    _go(repo, runner, api_running=True, stop_api=True)
    verbs = [next(a for a in c if a in {"stop", "run", "up"}) for c in runner.calls]
    assert verbs == ["stop", "run", "up"]
    assert runner.calls[-1][-2:] == ["--wait", "api"]


def test_a_failed_seed_still_starts_the_conduit_again_and_says_so(repo: Path) -> None:
    """Catches leaving the deployment with no API after a failed load."""
    runner = Runner(fail_seed=True)
    with pytest.raises(seed_internal.SeedFailed):
        _go(repo, runner, api_running=True, stop_api=True)
    assert runner.calls[-1][-2:] == ["--wait", "api"]


def test_a_conduit_that_was_not_running_is_not_started_by_the_seed(repo: Path) -> None:
    runner = Runner()
    _go(repo, runner)
    assert not any("up" in c for c in runner.calls)


def test_it_refuses_outside_a_checkout(repo: Path) -> None:
    """ADR-035 §C1: an internal dataset is never seeded from anything that left this project."""
    (repo.parent / ".git").rmdir()
    with pytest.raises(seed_internal.SeedRefused, match="checkout"):
        _go(repo, Runner())


def test_it_says_where_the_data_should_be_when_the_folder_is_missing(repo: Path) -> None:
    (repo.parent / "OspreyFlow_Data" / "PaySIM_Dataset").rmdir()
    with pytest.raises(seed_internal.SeedRefused, match="PaySIM_Dataset"):
        _go(repo, Runner())


def test_it_names_a_missing_demo_account_rather_than_seeding_without_grants(repo: Path) -> None:
    """A case nobody can open is what this exists to prevent."""
    runner = Runner()
    with pytest.raises(seed_internal.SeedRefused, match="register-sign-in"):
        _go(repo, runner, subs={ADMIN: "sub-admin-111"})
    assert runner.calls == []


def test_an_unknown_dataset_is_named(repo: Path) -> None:
    with pytest.raises(seed_internal.SeedRefused, match="unknown dataset"):
        seed_internal.seed_internal(
            "nope",
            repo,
            run=Runner(),
            lookup_subs=lambda d: SUBS,
            api_running=lambda c: False,
            stop_api=False,
        )


def test_the_seeds_own_report_is_returned_line_by_line_and_carries_no_secret(repo: Path) -> None:
    lines = _go(repo, Runner())
    assert any("70,000" in line for line in lines)
    call_text = " ".join(_seed_call(_run_and_return(repo)))
    assert "password" not in call_text.lower()
