"""The register's gate, round 2 (PL11): an image run by a literal `docker run`, the checks no case had
shown red, and the publish script's refusal.

Three things the verifier found in round 1, each shown red here before the code that answers it:

1. `default_disk_probe` (`harness/preflight/context.py`) runs `docker run --rm alpine df -k /` and
   every install and apply reaches it, but the derivation read only the top-level `harness/*.py` and
   only `ServiceImage(...)` and `*_IMAGE`: the image had no row and the gate stayed green.
2. The image's `os_packages` check, the duplicate-id check, the status and kind checks, the
   conditional row's "where read" and a `named_in` that is not a file had no planted case (rule 12:
   delete the block and nothing failed).
3. `scripts/publish_user_repo_update.sh` refused an owed test and a red GitHub but not an unsettled
   register: two release paths, one refusal.

Each fault is planted in the real register or the real source text, in the shape the code reads, and
each assertion names the fault (rule 15).

**The folders this test walks** (the scan row is written from this): under `OspreyFlow_Core`
everything `tools.licence_register.read_sources` reads and nothing more: `harness/**/*.py` (the
whole of `harness/`, `harness/preflight/` included), `providers/*.yaml`, `Dockerfile*` found by one
`rglob` under the **whole of `OspreyFlow_Core/`** (only `node_modules` and `.venv` left out: so a new
`FROM` in `cli/`, `scripts/`, `docs/` or any other folder is read), and the named files in that
module's `NAMED_FILES`. Under `OspreyFlow_Build`: `spec/LICENCE_REGISTER.yaml` and
`scripts/publish_user_repo_update.sh`, each by name. (The docstring of the acceptance file
`test_register.py`, which is frozen, says `services/`, `apps/` and `deploy/` for the Dockerfiles:
that is narrower than the code, and this is the account to write the scan row from.)
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tools import licence_register as reg
from tools.layout import BUILD

PUBLISH = BUILD / "scripts" / "publish_user_repo_update.sh"
CONTEXT = "harness/preflight/context.py"


def _violations(rows: list[dict[str, Any]], sources: dict[str, str]) -> list[str]:
    return reg.find_register_violations(rows, reg.named_by_code(sources))


def _real_rows() -> list[dict[str, Any]]:
    return copy.deepcopy(reg.load_register())


def _image_row(rows: list[dict[str, Any]], name: str = "valkey/valkey") -> dict[str, Any]:
    return next(r for r in rows if r["kind"] == "image" and r["name"] == name)


# --- 1. an image named only by a literal `docker run` -----------------------------------------------


def test_the_derivation_reads_the_whole_of_harness_not_only_its_top_level() -> None:
    assert CONTEXT in reg.read_sources()


def test_the_disk_probes_alpine_is_named_by_the_code_and_has_a_row() -> None:
    named = {(n.kind, n.name, n.pin) for n in reg.named_by_code(reg.read_sources())}
    assert ("image", "alpine", "latest") in named
    row = _image_row(_real_rows(), "alpine")
    assert row["pin"] == "latest" and row["os_packages"]["scan"] in reg.OS_SCANS


def test_removing_the_alpine_row_fails_the_gate_naming_the_file_that_runs_it() -> None:
    rows = [r for r in _real_rows() if r["name"] != "alpine"]
    found = _violations(rows, reg.read_sources())
    assert any("'alpine'" in v and "not in the register" in v and CONTEXT in v for v in found), (
        found
    )


def test_a_different_image_in_the_disk_probe_is_flagged_not_registered() -> None:
    sources = dict(reg.read_sources())
    text = sources[CONTEXT]
    changed = text.replace('"run", "--rm", "alpine", "df"', '"run", "--rm", "busybox:1.37", "df"')
    assert changed != text
    sources[CONTEXT] = changed
    found = _violations(_real_rows(), sources)
    assert any("'busybox'" in v and "not in the register" in v for v in found), found
    assert any("alpine" in v and "no code names" in v for v in found), found


@pytest.mark.parametrize(
    "call",
    [
        'subprocess.run(["docker", "run", "--rm", "debian:12-slim", "true"])',
        'subprocess.run([runtime, "run", "--rm", "--network", "none", "-v", "a:/b", '
        '"debian:12-slim", "true"])',
        'subprocess.run(["podman", "run", "-i", "debian:12-slim", "cat"])',
    ],
)
def test_a_literal_image_in_a_docker_run_in_a_new_harness_file_is_flagged(call: str) -> None:
    sources = dict(reg.read_sources())
    sources["harness/preflight/new_probe.py"] = f"import subprocess\n\nrunning = {call}\n"
    found = _violations(_real_rows(), sources)
    assert any(
        "'debian'" in v and "not in the register" in v and "new_probe.py" in v for v in found
    ), found


@pytest.mark.parametrize(
    "call",
    [
        'subprocess.run([*compose, "run", "--rm", "--no-deps", "api", "true"])',
        'subprocess.run(["docker", "compose", "run", "--rm", "api", "true"])',
        'subprocess.run(["docker", "run", "--rm", image, "true"])',
        'subprocess.run(["docker", "run", "--rm", *flags, "debian:12-slim", "true"])',
    ],
)
def test_a_compose_service_a_variable_and_a_splat_are_not_read_as_an_image(call: str) -> None:
    """A compose service name is not an image; a name in a variable is read where it is assigned (the
    `*_IMAGE` constants); and after a splat the position of the image is not known, so none is
    guessed."""
    sources = dict(reg.read_sources())
    before = {(n.kind, n.name) for n in reg.named_by_code(sources)}
    sources["harness/preflight/new_probe.py"] = f"import subprocess\n\nrunning = {call}\n"
    assert {(n.kind, n.name) for n in reg.named_by_code(sources)} == before


# --- 2. the checks no case had shown red ------------------------------------------------------------


def test_an_image_row_with_no_os_packages_fails() -> None:
    rows = _real_rows()
    del _image_row(rows)["os_packages"]
    found = reg.find_register_violations(rows, reg.named_by_code(reg.read_sources()))
    assert any("valkey/valkey" in v and "needs os_packages" in v for v in found), found


@pytest.mark.parametrize("scan", ["maybe", "", None, True])
def test_an_image_row_whose_scan_is_not_yes_no_or_partly_fails(scan: object) -> None:
    rows = _real_rows()
    _image_row(rows)["os_packages"] = {"scan": scan, "covered_by": "something"}
    found = _violations(rows, reg.read_sources())
    assert any("valkey/valkey" in v and "needs os_packages" in v for v in found), found


@pytest.mark.parametrize("covered", ["", "   ", None])
def test_an_image_row_that_does_not_say_how_its_packages_are_covered_fails(covered: object) -> None:
    rows = _real_rows()
    _image_row(rows)["os_packages"] = {"scan": "no", "covered_by": covered}
    found = _violations(rows, reg.read_sources())
    assert any(
        "valkey/valkey" in v and "does not say how the operating-system packages" in v
        for v in found
    ), found


def test_a_row_id_used_twice_fails() -> None:
    rows = _real_rows()
    rows[1]["id"] = rows[0]["id"]
    found = _violations(rows, reg.read_sources())
    assert any(f"the row id {rows[0]['id']!r} is used twice" in v for v in found), found


def test_an_unknown_status_fails() -> None:
    rows = _real_rows()
    row = _image_row(rows)
    row["status"] = "probably"
    found = _violations(rows, reg.read_sources())
    assert any(row["id"] in v and "the status 'probably' is not one of" in v for v in found), found


def test_an_unknown_kind_fails() -> None:
    rows = _real_rows()
    row = _image_row(rows)
    row["kind"] = "dataset"
    found = _violations(rows, reg.read_sources())
    assert any(row["id"] in v and "the kind 'dataset' is not one of" in v for v in found), found


def test_a_conditional_row_with_no_where_read_fails() -> None:
    rows = _real_rows()
    row = next(r for r in rows if r["status"] == "conditional")
    row["where_read"] = None
    found = _violations(rows, reg.read_sources())
    assert any(
        row["id"] in v and "conditional, but says nothing of where it was read" in v for v in found
    ), found


def test_a_named_in_that_is_not_a_file_fails() -> None:
    rows = _real_rows()
    row = _image_row(rows)
    row["named_in"] = [*row["named_in"], "harness/no_such_file.py"]
    found = _violations(rows, reg.read_sources())
    assert any(
        row["id"] in v and "named_in 'harness/no_such_file.py' is not a file" in v for v in found
    ), found


def test_a_missing_column_fails_for_every_column_the_register_requires() -> None:
    for column in reg.COLUMNS:
        rows = _real_rows()
        row = _image_row(rows)
        label = row["id"] if column != "id" else "?"
        del row[column]
        found = _violations(rows, reg.read_sources())
        assert any(label in v and f"no {column} column" in v for v in found), (column, found)


# --- 3. both release paths refuse an unsettled register ---------------------------------------------


def _publish_check() -> str:
    """The register's check as the publish script runs it: the statement from the script's text."""
    text = PUBLISH.read_text()
    found = re.search(
        r"^\(cd [^\n]*licence_register release-check\) \\\n\s*\|\| \{[^}]*exit 1; \}",
        text,
        re.M,
    )
    assert found, "the publish script does not run the register's release check"
    return found.group(0)


def test_the_publish_script_checks_the_register_before_it_exports_the_product() -> None:
    text = PUBLISH.read_text()
    check = _publish_check()
    assert 0 < text.index(check) < text.index("publish-user-repo COMMIT=HEAD")
    assert "nothing was published" in check


def test_the_publish_script_s_check_does_not_run_in_the_owner_s_bare_python3() -> None:
    """The check reads a YAML file; the owner's `python3` is not the project's environment and has no
    PyYAML to promise. The two checks beside it use only the standard library, this one cannot, so it
    runs in Core's own environment, the one `make publish-user-repo` on the next line uses."""
    check = _publish_check()
    assert "python3" not in check
    assert "OspreyFlow_Core" in check and ".venv/bin/python" in check


def _a_root_with_a_python3_that_has_no_pyyaml(root: Path) -> dict[str, str]:
    """`$ROOT` whose `ospreyflow` holds this checkout's Build and a Core with a `.venv/bin/python`
    that is the interpreter running the tests (it has PyYAML: the project's environment), and a
    `python3` first on the PATH that cannot import `yaml` (`-S`: no site-packages), as the owner's
    may not."""
    ospreyflow = root / "ospreyflow"
    (ospreyflow / "OspreyFlow_Core" / ".venv" / "bin").mkdir(parents=True)
    (ospreyflow / "OspreyFlow_Build").symlink_to(BUILD)
    venv_python = ospreyflow / "OspreyFlow_Core" / ".venv" / "bin" / "python"
    venv_python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    venv_python.chmod(0o755)
    (root / "bin").mkdir()
    bare = root / "bin" / "python3"
    bare.write_text(f'#!/bin/sh\nexec "{sys.executable}" -S "$@"\n')
    bare.chmod(0o755)
    return {**os.environ, "PATH": f"{root / 'bin'}:{os.environ['PATH']}"}


def _run_the_script_s_check(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the script's own statement, unchanged, with `$ROOT` a folder laid out as the owner's is
    and a `python3` on the PATH that has no PyYAML."""
    env = _a_root_with_a_python3_that_has_no_pyyaml(root)
    return subprocess.run(
        ["sh", "-c", f'ROOT="{root}"\n{_publish_check()}\necho went-on'],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_the_stand_in_python3_really_has_no_pyyaml(tmp_path: Path) -> None:
    """The fault planted is the shape the owner's machine may have: `python3 -m tools.licence_register`
    from Build ends in an import error, not in a refusal."""
    env = _a_root_with_a_python3_that_has_no_pyyaml(tmp_path)
    done = subprocess.run(
        ["python3", "-m", "tools.licence_register", "release-check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=BUILD,
        env=env,
    )
    assert done.returncode == 1 and "ModuleNotFoundError" in done.stderr, done.stderr


def test_the_publish_script_s_check_refuses_today_s_register_naming_what_is_left(
    tmp_path: Path,
) -> None:
    done = _run_the_script_s_check(tmp_path)
    assert done.returncode == 1 and "went-on" not in done.stdout
    assert "STOP" in done.stderr and "nothing was published" in done.stderr
    assert "ModuleNotFoundError" not in done.stderr and "Traceback" not in done.stderr, done.stderr
    assert "not settled" in done.stderr
    for name in reg.HELD_FOR_OWNER:
        assert f"held for the owner: {name!r}" in done.stderr
    for row in reg.load_register():
        if row["status"] == "unconfirmed":
            assert f"unconfirmed: {row['id']} {row['name']!r}" in done.stderr


def test_the_release_check_command_goes_on_with_a_settled_register(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _real_rows()
    for row in rows:
        if row["status"] == "unconfirmed":
            row.update(status="confirmed", licence="MIT", where_read="read", must_read=None)
    monkeypatch.setattr(reg, "load_register", lambda *a, **k: rows)
    monkeypatch.setattr(reg, "HELD_FOR_OWNER", frozenset())
    assert reg.main(["release-check"]) == 0
    assert "settled" in capsys.readouterr().out


def test_the_release_check_command_refuses_and_says_what_is_left(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert reg.main(["release-check"]) == 1
    assert "not settled" in capsys.readouterr().err


def test_the_release_check_command_with_no_verb_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert reg.main([]) == 2
    assert "release-check" in capsys.readouterr().err
