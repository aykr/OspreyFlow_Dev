"""`ospreyflow map` (`06_DECISIONS.md` ADR-147 decision 6): list, verify, prefetch and build, each
through the Conduit's own *Maps* code inside its container (`python -m services.api.map_admin`), so
the command line and *Admin › Maps* are one code with one audit.

What a mistake would do, and the case that catches it (rule 12):
- a verb run on the host instead of in the Conduit (a second code, its own files) —
  `test_each_verb_runs_the_conduit_s_own_maps_code_in_its_container`;
- a refusal inside the Conduit reported as success — `test_a_refusal_in_the_conduit_fails_the_verb`;
- the jar not where the Conduit's build reads it, or the build not said to run in the Conduit —
  `test_build_places_the_jar_and_says_where_the_build_runs`;
- a map extract taken for the jar — `test_build_refuses_a_jar_that_is_not_one`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .conftest import BASE_CONFIG, Rig

MAP_PATH = ["python", "-m", "services.api.map_admin"]


def _compose(rig: Rig) -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(rig.deployment / "deployment.env"),
        "-f", str(rig.deployment / "compose.yaml"),
    ]  # fmt: skip


def _installed(rig: Rig, tiles: Path) -> None:
    config = {**BASE_CONFIG, "components": {"storage": {"data": "/var/lib/osprey/data",
                                                         "tiles": str(tiles)}}}  # fmt: skip
    (rig.product / "osprey.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    rig.install_deployment()


def test_each_verb_runs_the_conduit_s_own_maps_code_in_its_container(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig, tmp_path / "tiles")
    rig.responses["list"] = [(0, "osm-local (default)  tier 1  key: none  Ready\n")]

    assert rig("map", "list") == 0
    assert "osm-local (default)  tier 1" in capsys.readouterr().out
    assert rig.captured[-1] == [*_compose(rig), "exec", "-T", "api", *MAP_PATH, "list"]

    assert rig("map", "verify") == 0
    assert rig("map", "prefetch") == 0
    assert rig("map", "build", "rutland") == 0
    argvs = [c.argv for c in rig.runner.calls]
    assert [a[a.index("services.api.map_admin") + 1:] for a in argvs] == [
        ["verify", "--by", argvs[0][-1]], ["prefetch", "--by", argvs[1][-1]],
        ["build", "rutland", "--by", argvs[2][-1]],
    ]  # fmt: skip
    assert all(a[: len(_compose(rig)) + 3] == [*_compose(rig), "exec", "-T", "api"] for a in argvs)
    assert all(a[-1].startswith("cli:") for a in argvs)


def test_a_refusal_in_the_conduit_fails_the_verb(rig: Rig, tmp_path: Path) -> None:
    _installed(rig, tmp_path / "tiles")
    rig.runner.fail["verify"] = 1
    assert rig("map", "verify") != 0


def test_build_places_the_jar_and_says_where_the_build_runs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The jar goes where the Conduit's build reads it; the build itself runs in the Conduit, which
    the command says, so a refusal there ("Java is not installed in the Conduit") reads as the
    Conduit's. `built/` is made and given to the Conduit before every `up`
    (`harness.ingest_uploads.prepare`), not here."""
    tiles = tmp_path / "tiles"
    _installed(rig, tiles)
    jar = tmp_path / "planetiler-0.9.jar"
    jar.write_bytes(b"PK jar")

    assert rig("map", "build", "rutland", "--planetiler-jar", str(jar)) == 0

    assert (tiles / "planetiler" / "planetiler.jar").read_bytes() == b"PK jar"
    assert "built by the Conduit, in its container" in capsys.readouterr().out


def test_build_refuses_a_jar_that_is_not_one(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig, tmp_path / "tiles")
    extract = tmp_path / "rutland.osm.pbf"
    extract.write_bytes(b"OSMHeader")
    assert rig("map", "build", "rutland", "--planetiler-jar", str(extract)) != 0
    assert "not a .jar" in capsys.readouterr().err
    assert rig.runner.calls == []
