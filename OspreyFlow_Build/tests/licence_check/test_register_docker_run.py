"""An image a `docker run` call names is an image a default install pulls (PL11, round 2's finding).

`default_disk_probe` in `harness/preflight/context.py` runs `docker run --rm alpine df -k /`, and every
apply or install calls it, so `alpine` (no tag: `latest`) is pulled and run. It is neither a `FROM`
line nor a `ServiceImage` nor a `*_IMAGE` constant, so the first derivation missed it and the gate
stayed green. These tests plant the fault at the shape the code has: the real file's text, one list
added or changed (rule 15), and one case that must NOT be read as an image (a compose service).

**The folders this test walks:** none of its own. It reads what
`tools.licence_register.read_sources` reads: see that module's docstring.
"""

from __future__ import annotations

from typing import Any

import pytest
from tools import licence_register as reg

PROBE = 'result = subprocess.run(\n        [runtime, "run", "--rm", "alpine", "df", "-k", "/"],'


@pytest.fixture
def sources() -> dict[str, str]:
    return dict(reg.read_sources())


def _violations(sources: dict[str, str]) -> list[str]:
    return reg.find_register_violations(reg.load_register(), reg.named_by_code(sources))


def test_the_real_disk_probe_is_read_as_the_alpine_image(sources: dict[str, str]) -> None:
    assert PROBE in sources["harness/preflight/context.py"], "the shape this derivation reads moved"
    named = [n for n in reg.named_by_code(sources) if n.kind == "image" and n.name == "alpine"]
    assert [(n.pin, n.files) for n in named] == [("latest", ("harness/preflight/context.py",))]


def test_the_register_has_a_row_for_alpine_and_it_is_the_probes_pin() -> None:
    rows = [r for r in reg.load_register() if r["kind"] == "image" and r["name"] == "alpine"]
    assert len(rows) == 1
    assert rows[0]["pin"] == "latest"
    assert "harness/preflight/context.py" in rows[0]["named_in"]
    assert rows[0]["os_packages"]["scan"] in reg.OS_SCANS


def test_removing_the_alpine_row_is_flagged(sources: dict[str, str]) -> None:
    rows = [r for r in reg.load_register() if r["name"] != "alpine"]
    found = reg.find_register_violations(rows, reg.named_by_code(sources))
    assert any("'alpine'" in v and "not in the register" in v for v in found), found


@pytest.mark.parametrize(
    "argv",
    [
        '[runtime, "run", "--rm", "busybox", "true"]',
        '["docker", "run", "--rm", "--user", "0:0", "--network", "none", "busybox:1.37", "true"]',
        '["podman", "run", "-i", "--rm", "--entrypoint", "sh", "example/other:3", "-c", "x"]',
    ],
)
def test_a_new_docker_run_image_in_the_harness_is_flagged(
    sources: dict[str, str], argv: str
) -> None:
    sources["harness/preflight/context.py"] += f"\n\ndef _more(runtime):\n    return {argv}\n"
    found = _violations(sources)
    image = argv.split('"')[-2] if "busybox" not in argv else "busybox"
    assert any(image.split(":")[0] in v and "not in the register" in v for v in found), found


def test_a_docker_run_image_in_the_cli_and_the_scripts_is_flagged(sources: dict[str, str]) -> None:
    for path in ("cli/ospreyflow/home.py", "scripts/seed_internal.py"):
        planted = dict(sources)
        planted[path] += '\n\nNEW = ["docker", "run", "--rm", "example/tool:9", "x"]\n'
        found = _violations(planted)
        assert any("example/tool" in v and path in v for v in found), (path, found)


@pytest.mark.parametrize(
    "argv",
    [
        # A compose service, not an image: the compose-only option says so.
        '[*compose, "run", "--rm", "--no-deps", "--entrypoint", "python", "api", "-m", "x"]',
        '["docker", "compose", "run", "--rm", "--no-deps", "api"]',
        # The image is a variable, a constant elsewhere.
        '["docker", "run", "--rm", image, "x"]',
        '["docker", "run", "--rm", *mounts, "api"]',
        # Not a container runtime at all.
        '["uv", "run", "--project", "python"]',
    ],
)
def test_what_is_not_a_docker_run_image_is_not_read_as_one(
    sources: dict[str, str], argv: str
) -> None:
    sources["harness/preflight/context.py"] += f"\n\ndef _more(runtime):\n    return {argv}\n"
    assert _violations(sources) == []


def test_the_gate_leg_fails_main_on_a_planted_docker_run_image(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import licence_check

    monkeypatch.setattr(licence_check, "run_pip_licenses", lambda extra: [])
    monkeypatch.setattr("sys.argv", ["licence_check"])
    real = reg.read_sources()
    planted: dict[str, Any] = {
        **real,
        "harness/preflight/context.py": real["harness/preflight/context.py"].replace(
            '"run", "--rm", "alpine"', '"run", "--rm", "busybox"'
        ),
    }
    assert planted["harness/preflight/context.py"] != real["harness/preflight/context.py"]
    monkeypatch.setattr(reg, "read_sources", lambda *a, **k: planted)
    assert licence_check.main() == 1
    err = capsys.readouterr().err
    assert "busybox" in err and "alpine" in err
