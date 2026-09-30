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
    dataset: str = "paysim",
    permitted: bool = True,
) -> list[str]:
    return seed_internal.seed_internal(
        dataset,
        repo,
        run=runner,
        lookup_subs=lambda directory: SUBS if subs is None else subs,
        api_running=lambda compose: api_running,
        stop_api=stop_api,
        permitted=lambda name, use: permitted,
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


# --- Enron (real data), Fixture Corp and HMP (ADR-053 Amendment 1, ADR-052 Amendment 9) ---


def _with_enron(repo: Path) -> None:
    (repo.parent / "OspreyFlow_Data" / "Enron_Mails" / "smith-a").mkdir(parents=True)


def test_enron_is_refused_on_the_host_without_an_exceptions_entry_and_nothing_is_started(
    repo: Path,
) -> None:
    """Catches real data being loaded because the container cannot see the exceptions list: the
    host is the one place that can, so it must check before starting anything."""
    _with_enron(repo)
    runner = Runner()
    with pytest.raises(seed_internal.SeedRefused, match="exceptions"):
        _go(repo, runner, dataset="enron", permitted=False)
    assert runner.calls == []


def test_enron_asks_the_exceptions_list_about_this_dataset_and_use(repo: Path) -> None:
    """Catches a check for the wrong name or use, which would admit or refuse the wrong thing."""
    _with_enron(repo)
    asked: list[tuple[str, str]] = []
    seed_internal.seed_internal(
        "enron",
        repo,
        run=Runner(),
        lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False,
        permitted=lambda name, use: asked.append((name, use)) or True,
    )
    assert asked == [("enron", "owner_run_demonstration")]


def test_enron_passes_the_hosts_attestations_and_its_own_case_name(repo: Path) -> None:
    """The container cannot see the exceptions list or a `.git`, so it is told, and the case is
    the one ADR-053 names, shared only with the two demo accounts."""
    _with_enron(repo)
    runner = Runner()
    _go(repo, runner, dataset="enron")
    call = _seed_call(runner)
    assert call[call.index("-m") + 1] == "scripts.seed_enron"
    assert "--attested-permission" in call and "--attested-checkout" in call
    assert call[call.index("--case-name") + 1] == "Enron corpus (real data, this machine only)"
    assert f"{SUBS[ADMIN]}=author" in call and f"{SUBS[ANALYST]}=editor" in call


def test_a_synthetic_dataset_is_never_given_a_permission_attestation(repo: Path) -> None:
    """Catches the attestation leaking to a seed that has no such check."""
    runner = Runner()
    _go(repo, runner)
    assert "--attested-permission" not in _seed_call(runner)


@pytest.mark.parametrize(
    ("dataset", "module"),
    [("hmp", "scripts.seed_hmp_fixture"), ("fixture-corp", "scripts.seed_fixture_corp")],
)
def test_the_synthetic_demos_load_into_named_shared_cases_with_no_data_folder(
    repo: Path, dataset: str, module: str
) -> None:
    """Catches the demos still needing a raw case id, and a data mount or data flags they do not
    take (these seeds generate their own data)."""
    runner = Runner()
    _go(repo, runner, dataset=dataset)
    call = _seed_call(runner)
    assert call[call.index("-m") + 1] == module
    assert "--case-name" in call and "--investigation-scope" not in call
    assert call[call.index("--org-unit") + 1] == "verify"
    assert f"{SUBS[ADMIN]}=author" in call and f"{SUBS[ANALYST]}=editor" in call
    assert "--data-dir" not in call and "--attested-checkout" not in call
    assert not any(a.endswith(":/internal-data:ro") for a in call)


def test_an_unknown_dataset_lists_the_known_ones(repo: Path) -> None:
    with pytest.raises(seed_internal.SeedRefused, match="enron.*fixture-corp.*hmp.*paysim"):
        _go(repo, Runner(), dataset="nope")


# --- progress is shown as it happens ---


def test_the_real_runner_echoes_each_line_as_it_arrives_and_still_returns_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Seen: a seed that takes many minutes printed nothing until it finished, so it looked hung.
    Catches a runner that only captures."""
    import sys

    out = seed_internal._run([sys.executable, "-c", "print('one', flush=True); print('two')"])
    assert out.split() == ["one", "two"]
    shown = capsys.readouterr().out
    assert "one" in shown and "two" in shown


def test_the_real_runner_raises_with_the_failure_text_when_the_command_fails() -> None:
    """Catches losing the error text now that both streams are read as one."""
    import sys

    with pytest.raises(seed_internal.SeedFailed, match="boom"):
        seed_internal._run([sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"])


# --- replacing an interrupted load, and the graph sample ---


def _with(repo: Path, **kwargs: object) -> Runner:
    runner = Runner()
    seed_internal.seed_internal(
        "paysim",
        repo,
        run=runner,
        lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False,
        **kwargs,  # type: ignore[arg-type]
    )
    return runner


def test_replace_graph_is_passed_to_the_seed_only_when_asked_for(repo: Path) -> None:
    """Catches the flag never reaching the container, or being on for every run."""
    assert "--replace-graph" not in _seed_call(_with(repo))
    assert "--replace-graph" in _seed_call(_with(repo, replace_graph=True))


def test_paysim_is_given_a_graph_sample_by_default_and_all_can_be_asked_for(repo: Path) -> None:
    """The full graph takes many hours to write; the sample is the default, the full graph an
    explicit choice. Catches an unbounded default."""
    call = _seed_call(_with(repo))
    assert call[call.index("--graph-fraud-rows") + 1] == str(seed_internal.DEFAULT_GRAPH_SAMPLE)
    call = _seed_call(_with(repo, graph_fraud_rows=1200))
    assert call[call.index("--graph-fraud-rows") + 1] == "1200"
    assert "--graph-fraud-rows" not in _seed_call(_with(repo, graph_fraud_rows=0))


def test_a_dataset_with_no_graph_sample_is_never_given_one(repo: Path) -> None:
    """Catches the sample flag reaching a seed that does not take it."""
    (repo.parent / "OspreyFlow_Data" / "Enron_Mails" / "a").mkdir(parents=True)
    runner = Runner()
    seed_internal.seed_internal(
        "enron",
        repo,
        run=runner,
        lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False,
        permitted=lambda name, use: True,
    )
    assert "--graph-fraud-rows" not in _seed_call(runner)


def test_the_command_line_accepts_the_new_flags(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches `make`'s command line not knowing the flags."""
    seen: dict[str, object] = {}

    def fake(dataset: str, **kwargs: object) -> list[str]:
        seen.update(kwargs, dataset=dataset)
        return []

    monkeypatch.setattr(seed_internal, "seed_internal", fake)
    argv = ["paysim", "--stop-api", "--replace-graph", "--graph-fraud-rows", "800"]
    assert seed_internal.main(argv) == 0
    assert seen["replace_graph"] is True and seen["graph_fraud_rows"] == 800
    assert seen["stop_api"] is True
    seen.clear()
    assert seed_internal.main(["paysim", "--graph-fraud-rows", "all"]) == 0
    assert seen["graph_fraud_rows"] == 0


# --- reading the graph without changing it ---


def test_inspect_runs_the_seed_read_only_without_stopping_the_conduit_or_making_a_case(
    repo: Path,
) -> None:
    """Catches an inspection that stops the Conduit, needs the demo accounts, or creates a case."""
    runner = Runner()
    seed_internal.seed_internal(
        "paysim",
        repo,
        run=runner,
        lookup_subs=lambda directory: {},
        api_running=lambda compose: True,
        inspect=True,
        inspect_record="#169:80",
    )
    call = _seed_call(runner)
    assert "--inspect" in call and call[call.index("--inspect-record") + 1] == "#169:80"
    assert "--case-name" not in call and "--grant" not in call
    assert not any(c[1:] and "stop" in c for c in runner.calls)


def test_the_command_line_accepts_inspect(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(seed_internal, "seed_internal", lambda dataset, **kw: seen.update(kw) or [])
    assert seed_internal.main(["paysim", "--inspect", "--inspect-record", "#169:80"]) == 0
    assert seen["inspect"] is True and seen["inspect_record"] == "#169:80"


def test_an_inspection_does_not_say_the_dataset_is_loaded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seen: --inspect ended with 'paysim is loaded', which was false and misleading."""
    monkeypatch.setattr(seed_internal, "seed_internal", lambda dataset, **kw: [])
    assert seed_internal.main(["paysim", "--inspect"]) == 0
    out = capsys.readouterr().out
    assert "is loaded" not in out and "nothing was changed" in out
