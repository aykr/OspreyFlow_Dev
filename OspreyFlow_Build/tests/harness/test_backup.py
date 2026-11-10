"""`ospreyflow backup` on Small on a server of your own (ADR-114 Amendment 33 decision 5; drop 2,
unit 6): where the set is written, and what is never in it.

The stores' own dumps need the running deployment and are proved by the live exit test
(`test_restore_exit_test.py`); these cases are about the two things this mode adds — the folder
`server.backups` names, and the organisation's certificate key, which lives outside the deployment
and must never be copied into a set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness import backup, site

from schemas.deployment import OspreyConfig

from .tls_fixtures import write_set


def _own_server(folder: Path, backups: str | None = "/srv/ospreyflow/backups") -> OspreyConfig:
    files = write_set(folder / "tls")
    raw: dict[str, object] = {
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.internal",
                    "tls": {"certificate": str(files.certificate), "key": str(files.key),
                            "ca": str(files.ca)}},
    }  # fmt: skip
    if backups:
        raw["components"] = {"storage": {"backups": backups}}
    return OspreyConfig.model_validate(raw)


@pytest.fixture
def no_resolver_changes(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """`answer_the_deployment_here` reached, recorded, without changing this process's resolver
    or trust store for the tests after it."""
    seen: dict[str, list[str]] = {"trusted": []}
    monkeypatch.setattr(site, "_HERE", {})
    monkeypatch.setattr(site, "_answer_here", lambda: None)
    monkeypatch.setattr(site, "_trust", lambda files: seen["trusted"].extend(files))
    return seen


def _cloud_small(backups: str | None = None) -> OspreyConfig:
    raw: dict[str, object] = {
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.org"},
        "external": {"postgres": {"host": "db.example.org"}},
    }
    if backups:
        raw["components"] = {"storage": {"backups": backups}}
    return OspreyConfig.model_validate(raw)


def test_every_profile_backs_up_to_its_configured_folder(tmp_path: Path) -> None:
    """ADR-114 Amendment 37 decisions 1 and 3: `components.storage.backups` is read for every
    profile (local-lite, a cloud's Small, Small on a server of your own), and a set goes to that
    folder's subfolder for the deployment (Amendment 33 decision 5 read it on a server only)."""
    lite = OspreyConfig.model_validate({"components": {"storage": {"backups": str(tmp_path / "l")}}})
    assert backup.default_out_root(lite) == tmp_path / "l" / "local-lite"
    assert backup.default_out_root(_cloud_small(str(tmp_path / "c"))) == tmp_path / "c" / "small"
    server = _own_server(tmp_path, backups=str(tmp_path / "s"))
    assert backup.default_out_root(server) == tmp_path / "s" / "small"
    # The placeholder a server named on purpose is still that server's folder (Amendment 33).
    named = _own_server(tmp_path, backups=backup.LEGACY_PLACEHOLDER)
    assert backup.default_out_root(named) == Path(backup.LEGACY_PLACEHOLDER) / "small"
    # And so is the schema's default when the server's settings leave it out (Amendment 38
    # decision 1): the guided page writes it out and a hand-written file may not, one folder either
    # way.
    unset = _own_server(tmp_path, backups=None)
    assert backup.backups_folder(unset) == (Path(backup.LEGACY_PLACEHOLDER), None)


def test_a_config_without_a_backups_folder_falls_back_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 2: an `osprey.yaml` written before Amendment 37 names no folder — none at all, or
    the schema's `/var/lib/osprey/backups` placeholder the committed defaults carry, which nothing
    off a server ever asked for — so the set goes to `~/OspreyFlow/backups`, and the backup says
    so in its output."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    fallback = tmp_path / "home" / "OspreyFlow" / "backups"
    assert backup.LEGACY_PLACEHOLDER == "/var/lib/osprey/backups"
    for raw in ({}, {"components": {"storage": {"backups": backup.LEGACY_PLACEHOLDER}}},
                {"components": {"storage": {"backups": backup.LEGACY_PLACEHOLDER + "/"}}},
                {"components": {"storage": {"backups": " "}}}):  # fmt: skip
        config = OspreyConfig.model_validate(raw)
        root, notice = backup.backups_folder(config)
        assert root == fallback
        assert notice is not None and str(fallback) in notice and "folders.backups" in notice
        assert backup.default_out_root(config) == fallback / "local-lite"
    assert backup.backups_folder(_cloud_small(str(tmp_path / "c")))[1] is None
    # Said where the operator reads it: the backup's own output.
    path = tmp_path / "osprey.yaml"
    path.write_text("{}\n")
    (tmp_path / "generated" / "local-lite").mkdir(parents=True)
    (tmp_path / "generated" / "local-lite" / "compose.yaml").write_text("services: {}\n")
    seen: dict[str, object] = {}

    def run_backup(**kwargs: object) -> Path:
        seen.update(kwargs)
        raise backup.BackupFailed("graph", "stopped by the test")

    monkeypatch.setattr(backup, "run_backup", run_backup)
    lines: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: lines.append(" ".join(map(str, a))))
    assert backup.main(["--config", str(path), "--generated-root", str(tmp_path / "generated")]) == 1
    assert seen["out_root"] == fallback / "local-lite"
    assert any(str(fallback) in line and "folders.backups" in line for line in lines), lines


def test_no_backup_is_written_inside_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 2: with no folder named, the set never lands in the checkout's `backups/` (where
    three local-lite sets, 16 GB, were synced with `~/Documents`); and the one place a set's folder
    is made refuses one inside the checkout, whatever chose it."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    checkout = backup.checkout_root().resolve()
    for raw in ({}, {"components": {"storage": {"backups": backup.LEGACY_PLACEHOLDER}}}):
        chosen = backup.default_out_root(OspreyConfig.model_validate(raw)).resolve()
        assert not chosen.is_relative_to(checkout), chosen
    assert not hasattr(backup, "DEFAULT_BACKUP_ROOT")
    # A stand-in checkout, so a regression here writes into a temporary folder, not the real one.
    stand_in = tmp_path / "checkout"
    stand_in.mkdir()
    monkeypatch.setattr(backup, "REPO_ROOT", stand_in)
    with pytest.raises(backup.BackupFailed, match="inside the checkout") as refused:
        backup.new_set_folder(stand_in / "backups" / "local-lite", "local-lite")
    assert str(stand_in.resolve()) in refused.value.detail
    assert not (stand_in / "backups").exists()


def test_an_out_root_from_tilde_is_the_home_folder_never_a_folder_named_tilde(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ospreyflow backup --out-root=~/x`: the shell expands no `~` after `=`, so the harness gets
    `~/x` itself, run from the product folder. The folder checked and the folder written must be
    the one Path, `$HOME/x`; before, the check expanded `~` and `mkdir` did not, so the set landed in
    `<product>/~/x/`, inside the checkout. Found by the orchestrator's independent review."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    stand_in = tmp_path / "checkout"
    product = stand_in / "OspreyFlow_Core"
    product.mkdir(parents=True)
    (stand_in / ".git").write_text("gitdir: elsewhere\n")
    monkeypatch.setattr(backup, "REPO_ROOT", product)
    monkeypatch.chdir(product)
    made = backup.new_set_folder(Path("~/x"), "local-lite")
    assert made.parent == home / "x"
    assert not (product / "~").exists()
    # And `main` hands the store steps that same folder.
    path = tmp_path / "osprey.yaml"
    path.write_text("{}\n")
    (tmp_path / "generated" / "local-lite").mkdir(parents=True)
    (tmp_path / "generated" / "local-lite" / "compose.yaml").write_text("services: {}\n")
    seen: dict[str, object] = {}

    def run_backup(**kwargs: object) -> Path:
        seen.update(kwargs)
        raise backup.BackupFailed("graph", "stopped by the test")

    monkeypatch.setattr(backup, "run_backup", run_backup)
    argv = ["--config", str(path), "--generated-root", str(tmp_path / "generated"), "--out-root=~/y"]
    assert backup.main(argv) == 1
    assert seen["out_root"] == home / "y"
    assert not (product / "~").exists()


def test_a_folder_anywhere_in_the_git_checkout_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The checkout is the git checkout, `OspreyFlow_Core`'s parent when that holds `.git` (a file
    in a worktree): its root and `OspreyFlow_Build/` are as much the checkout as `OspreyFlow_Core/`,
    and only `OspreyFlow_Core/backups/` was ever gitignored. Found by the lane-reviewer."""
    root = tmp_path / "checkout"
    core = root / "OspreyFlow_Core"
    (root / "OspreyFlow_Build").mkdir(parents=True)
    core.mkdir()
    (root / ".git").write_text("gitdir: elsewhere\n")
    monkeypatch.setattr(backup, "REPO_ROOT", core)
    assert backup.checkout_root() == root
    for inside in (root / "backups", root / "OspreyFlow_Build" / "sets", root, core / "backups"):
        with pytest.raises(backup.BackupFailed, match="inside the checkout"):
            backup.new_set_folder(inside / "local-lite", "local-lite")
    assert sorted(p.name for p in root.iterdir()) == [".git", "OspreyFlow_Build", "OspreyFlow_Core"]
    made = backup.new_set_folder(tmp_path / "elsewhere" / "local-lite", "local-lite")
    assert made.parent == tmp_path / "elsewhere" / "local-lite"


def test_the_checkout_spelt_another_way_is_still_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compared by the folder it is, not its spelling: through a link to it, and, on a disk that
    ignores letter case (macOS's default), in another case. Found by the lane-reviewer."""
    stand_in = tmp_path / "Checkout"
    stand_in.mkdir()
    monkeypatch.setattr(backup, "REPO_ROOT", stand_in)
    (tmp_path / "link").symlink_to(stand_in)
    with pytest.raises(backup.BackupFailed, match="inside the checkout"):
        backup.new_set_folder(tmp_path / "link" / "backups", "local-lite")
    # A link followed by `..`: the folder made is the link's parent's sibling, inside the checkout
    # (second lane-reviewer pass).
    (stand_in / "core").mkdir()
    (tmp_path / "to-core").symlink_to(stand_in / "core")
    with pytest.raises(backup.BackupFailed, match="inside the checkout"):
        backup.new_set_folder(tmp_path / "to-core" / ".." / "bk", "local-lite")
    assert not (stand_in / "bk").exists() and not (tmp_path / "bk").exists()
    # A deployment name that climbs out of the folder it is given is refused as well.
    with pytest.raises(backup.BackupFailed, match="name"):
        backup.new_set_folder(tmp_path / "ok", "x/../../Checkout")
    other_case = tmp_path / "checkout"
    if not other_case.exists():
        pytest.skip("this disk tells letter cases apart, so the other spelling is another folder")
    with pytest.raises(backup.BackupFailed, match="inside the checkout"):
        backup.new_set_folder(other_case / "backups", "local-lite")
    assert not (stand_in / "backups").exists()


def test_an_out_root_inside_the_checkout_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Decision 2: `--out-root` is still honoured, but one inside the checkout is refused, naming
    the checkout, before anything is run — by its relative spelling too."""
    path = tmp_path / "osprey.yaml"
    path.write_text(yaml.safe_dump({"components": {"storage": {"backups": str(tmp_path / "b")}}}))
    (tmp_path / "generated" / "local-lite").mkdir(parents=True)
    (tmp_path / "generated" / "local-lite" / "compose.yaml").write_text("services: {}\n")
    ran: list[object] = []
    monkeypatch.setattr(backup, "run_backup", lambda **kwargs: ran.append(kwargs))
    monkeypatch.chdir(backup.REPO_ROOT)
    common = ["--config", str(path), "--generated-root", str(tmp_path / "generated")]
    for inside in (str(backup.REPO_ROOT / "backups"), "backups", "deploy/../backups"):
        assert backup.main([*common, "--out-root", inside]) == 1
        said = capsys.readouterr().err
        assert "inside the checkout" in said and str(backup.checkout_root().resolve()) in said
    assert ran == []
    # Outside it, the folder given is used as it is.
    def run_backup(**kwargs: object) -> Path:
        ran.append(kwargs["out_root"])
        raise backup.BackupFailed("graph", "stopped by the test")

    monkeypatch.setattr(backup, "run_backup", run_backup)
    assert backup.main([*common, "--out-root", str(tmp_path / "elsewhere")]) == 1
    assert ran == [tmp_path / "elsewhere"]


def test_two_deployments_sets_go_to_their_own_subfolders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 3 (ADR-138's rule): two deployments sharing one backups folder each write to
    `<folder>/<deployment name>/`, so a set of one is never among the other's."""
    monkeypatch.setattr(backup, "git_sha", lambda: "abc1234")
    folder = tmp_path / "backups"

    def named(name: str) -> OspreyConfig:
        return OspreyConfig.model_validate(
            {"deployment": {"name": name}, "components": {"storage": {"backups": str(folder)}}}
        )

    alpha, beta = backup.default_out_root(named("alpha")), backup.default_out_root(named("beta"))
    assert (alpha, beta) == (folder / "alpha", folder / "beta")
    made_alpha = backup.new_set_folder(alpha, "alpha")
    made_beta = backup.new_set_folder(beta, "beta")
    assert made_alpha.parent == folder / "alpha" and made_beta.parent == folder / "beta"
    assert [p.name for p in (folder / "alpha").iterdir()] == [made_alpha.name]
    assert [p.name for p in (folder / "beta").iterdir()] == [made_beta.name]


def test_backup_main_writes_to_the_configured_folder_reaching_the_servers_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_resolver_changes: dict[str, list[str]]
) -> None:
    config = _own_server(tmp_path, backups=str(tmp_path / "backups"))
    path = tmp_path / "osprey.yaml"
    path.write_text(yaml.safe_dump(config.model_dump(mode="json", exclude_defaults=True)))
    (tmp_path / "generated" / "small").mkdir(parents=True)
    (tmp_path / "generated" / "small" / "compose.yaml").write_text("services: {}\n")
    seen: dict[str, object] = {}

    def run_backup(**kwargs: object) -> Path:
        seen.update(kwargs)
        # What the identity export reaches: the deployment's own identity name, here.
        seen["id"] = site._HERE.get("id.osprey.example.internal")
        raise backup.BackupFailed("graph", "stopped by the test")

    monkeypatch.setattr(backup, "run_backup", run_backup)
    assert backup.main(["--config", str(path), "--generated-root", str(tmp_path / "generated")]) == 1
    assert seen["out_root"] == tmp_path / "backups" / "small"
    assert seen["id"] == "127.0.0.1"
    assert str(config.network.tls.certificate) in no_resolver_changes["trusted"]  # type: ignore[union-attr]


def test_a_backup_never_carries_the_tls_key(tmp_path: Path) -> None:
    """Decision 5 and §6.1: the set's configuration is the deployment's settings and rendered
    files — never the organisation's certificate key (mounted from where it is, never copied), and
    never `deployment.env`'s secrets."""
    config = _own_server(tmp_path)
    assert config.network.tls is not None
    key = Path(config.network.tls.key).read_bytes()
    deployment = tmp_path / "generated" / "small"
    deployment.mkdir(parents=True)
    (deployment / "compose.yaml").write_text(
        yaml.safe_dump({"services": {"proxy": {"volumes": [
            f"{config.network.tls.certificate}:/certs/cert.pem:ro",
            f"{config.network.tls.key}:/certs/key.pem:ro"]}}})
    )  # fmt: skip
    (deployment / "realm.json").write_text("{}\n")
    (deployment / "tls-fingerprint").write_text("ab:cd\n")
    (deployment / "deployment.env").write_text("OSPREY_ORG_SIGN_IN_SECRET=never-in-a-backup\n")
    target = tmp_path / "set"
    written = backup.backup_configuration(deployment / "compose.yaml", target)
    assert {item for item, _path in written} == {"configuration"}
    names = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    assert "config/compose.yaml" in names and "config/realm.json" in names
    for file in target.rglob("*"):
        if file.is_file():
            body = file.read_bytes()
            assert key not in body and b"PRIVATE KEY" not in body, file
            assert b"never-in-a-backup" not in body, file


def test_a_backup_set_is_readable_by_its_owner_only(tmp_path: Path) -> None:
    """A set holds the case data and the people's identities with the dashboards' client secrets;
    on a server it sits in a folder of its own (`server.backups`), so it is made owner-only."""
    target = backup.new_set_folder(tmp_path / "backups", "small")
    assert target.parent == tmp_path / "backups"
    assert target.stat().st_mode & 0o777 == 0o700
