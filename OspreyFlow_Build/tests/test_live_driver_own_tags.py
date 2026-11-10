"""P5b's live driver (`process/lanes/platform-b/gates/p5b_live_update.py`) on a shared server: what
it removes, what it puts back, and what its after-check fails on (CARRIES' owed-proof row, the
conditions the orchestrator set after its first cleanup deleted three of another lane's images, 10
November 2026).

The fake `docker` keeps a real table of tags and the image ID each names, and refuses what docker
   refuses (rule 15: `rmi` of a name it does not hold). Another lane works on the same table while
   the run goes on: it rebuilds a tag the run made, and it makes tags of its own.
- A tag the run made is removed only while it still names the ID the run made —
  `test_a_tag_the_run_made_is_removed_only_while_it_names_the_run_s_image`.
- A tag that existed before is put back to its old ID —
  `test_a_tag_that_existed_before_is_put_back`.
- The after-check fails on a tag changed or left —
  `test_the_after_check_fails_on_a_tag_changed_or_left`.
- The guard: a removal names this project's own containers, volumes and project alone, and an image
  is removed only through the run's record —
  `test_the_guard_refuses_another_s_volume_container_project_or_image`; in teardown a refusal is
  said and the cleanup goes on — `test_a_refusal_in_teardown_never_stops_the_cleanup`.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

DRIVER = Path(__file__).resolve().parents[1] / "process/lanes/platform-b/gates/p5b_live_update.py"


def _driver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("p5b_live_update", DRIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDocker:
    """`docker tag` and `rmi` over a table of tag -> image ID, and the images that exist; `inspect`
    reads it. As docker does, a tag of an image that no longer exists is refused, and `prune`
    deletes every image no tag names: on the server an image left untagged by a rebuild was gone
    by teardown (11 November 2026)."""

    def __init__(self, tags: dict[str, str]) -> None:
        self.tags = dict(tags)
        self.images = set(tags.values())
        self.calls: list[list[str]] = []

    def inspect(self, name: str) -> str | None:
        return self.tags.get(name)

    def build(self, name: str, image_id: str) -> None:
        self.images.add(image_id)
        self.tags[name] = image_id

    def prune(self) -> None:
        self.images &= set(self.tags.values())

    def __call__(self, argv: Sequence[str], check: bool = False, **_: Any) -> Any:
        argv = list(argv)
        self.calls.append(argv)
        verb, *rest = argv[1:]
        if verb == "tag":
            source, target = rest
            image_id = self.tags.get(source, source)
            if image_id not in self.images:
                if check:
                    raise subprocess.CalledProcessError(1, argv)
                return subprocess.CompletedProcess(argv, 1)
            self.tags[target] = image_id
        elif verb == "rmi":
            for name in rest:
                if name not in self.tags:
                    if check:
                        raise subprocess.CalledProcessError(1, argv)
                    continue
                del self.tags[name]
        return subprocess.CompletedProcess(argv, 0)


BEFORE = {"osprey/superset:local": "sha256:old-superset", "python:3.12-slim": "sha256:py"}


def _ran(docker: FakeDocker) -> Any:
    """The run: its old images held first, then its build makes `osprey/api:local` and rebuilds
    `osprey/superset:local`, leaving the old superset image untagged but for the hold."""
    images = _driver().OwnImages(dict(docker.tags), inspect=docker.inspect, runner=docker)
    images.hold(run="r1")
    docker.build("osprey/api:local", "sha256:ours-api")
    docker.build("osprey/superset:local", "sha256:ours-superset")
    images.claim(["osprey/api:local", "osprey/superset:local"])
    return images


def test_a_tag_the_run_made_is_removed_only_while_it_names_the_run_s_image() -> None:
    docker = FakeDocker(BEFORE)
    images = _ran(docker)
    # Mid-run, another lane builds osprey/api:local again, and tags an image of its own.
    docker.tags["osprey/api:local"] = "sha256:another-lane"
    docker.tags["localhost:5001/ospreyflow/api:9fa5b19a"] = "sha256:p7"
    said = images.restore()
    assert docker.tags["osprey/api:local"] == "sha256:another-lane"
    assert docker.tags["localhost:5001/ospreyflow/api:9fa5b19a"] == "sha256:p7"
    assert not any(c[1] == "rmi" and "osprey/api:local" in c for c in docker.calls)
    assert any("osprey/api:local" in line and "another" in line for line in said), said


def test_a_tag_that_existed_before_is_put_back() -> None:
    docker = FakeDocker(BEFORE)
    images = _ran(docker)
    docker.prune()  # another lane prunes while the run goes on: the hold keeps the old image
    images.restore()
    assert docker.tags["osprey/superset:local"] == "sha256:old-superset"
    assert "osprey/api:local" not in docker.tags  # the run's own, new: removed
    assert docker.tags["python:3.12-slim"] == "sha256:py"
    assert images.made_ids() == {"sha256:ours-api", "sha256:ours-superset"}
    assert not any(tag.startswith("osprey-p5b-hold/") for tag in docker.tags), docker.tags
    assert images.unrestored() == []


def test_the_after_check_fails_on_a_tag_changed_or_left() -> None:
    """It fails on what the run did, and lists, without failing, what another lane did on the same
    server meanwhile (on 11 November its test images and containers came and went during the
    run)."""
    driver = _driver()
    made = {"sha256:ours"}
    claimed = {"osprey/superset:local"}
    assert driver.tags_changed(BEFORE, dict(BEFORE), made, claimed) == []
    # Another lane's new tag, or one of its own it changed, is its business, not a failure.
    assert driver.tags_changed(BEFORE, {**BEFORE, "theirs:1": "sha256:t"}, made, claimed) == []
    theirs = {**BEFORE, "python:3.12-slim": "sha256:rebuilt-by-another"}
    assert driver.tags_changed(BEFORE, theirs, made, claimed) == []
    # A tag the run's build moved, not put back; the run's image or a hold left behind.
    moved = {**BEFORE, "osprey/superset:local": "sha256:ours"}
    assert driver.tags_changed(BEFORE, moved, made, claimed) == ["osprey/superset:local"]
    left = {**BEFORE, "osprey/api:local": "sha256:ours"}
    assert driver.tags_changed(BEFORE, left, made, claimed) == ["osprey/api:local"]
    held = {**BEFORE, "osprey-p5b-hold/osprey-superset-local:r1": "sha256:old-superset"}
    assert driver.tags_changed(BEFORE, held, made, claimed) == [
        "osprey-p5b-hold/osprey-superset-local:r1"
    ]
    # A pre-existing tag the run claimed and could not put back is the run's failure too.
    gone = {"python:3.12-slim": "sha256:py"}
    assert driver.tags_changed(BEFORE, gone, made, claimed) == ["osprey/superset:local"]


def test_a_rebuilt_image_pruned_meanwhile_is_still_put_back_because_it_was_held() -> None:
    """Without the hold, the old superset image is untagged by the build and pruned, and the
    put-back has nothing to tag: the failure seen on the server."""
    docker = FakeDocker(BEFORE)
    images = _driver().OwnImages(dict(docker.tags), inspect=docker.inspect, runner=docker)
    docker.build("osprey/superset:local", "sha256:ours-superset")  # no hold first
    images.claim(["osprey/superset:local"])
    docker.prune()
    images.restore()
    assert images.unrestored() == ["osprey/superset:local"]


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "home" / "d").mkdir(parents=True)
    (tmp_path / "home" / "d" / "compose.yaml").write_text("name: osprey-p5b-test\n")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "compose.yaml").write_text("name: osprey-small\n")
    return tmp_path / "home"


def test_the_guard_refuses_another_s_volume_container_project_or_image(home: Path) -> None:
    driver = _driver()
    mine = str(home / "d" / "compose.yaml")
    theirs = str(home.parent / "other" / "compose.yaml")
    envfile = str(home / "d" / "deployment.env")
    allowed = [
        ["docker", "compose", "-f", mine, "down", "-v"],
        ["docker", "compose", "--project-name", "osprey-p5b-test", "-f", mine, "down", "-v"],
        # The rollback's own shape (`harness.update._compose_argv`): the env file first, no -p.
        ["docker", "compose", "--env-file", envfile, "-f", mine, "down", "-v"],
        ["docker", "volume", "rm", "osprey-p5b-test_osprey-data"],
        ["docker", "rm", "-v", "osprey-p5b-test-api-1"],
        ["docker", "compose", "-f", mine, "up", "-d"],  # nothing removed: passed as it is
    ]
    for argv in allowed:
        assert driver.guarded(argv, home) is not None, argv
    assert driver.guarded(allowed[0], home)[:4] == ["docker", "compose", "-p", "osprey-p5b-test"]
    refused = [
        ["docker", "compose", "-f", theirs, "down", "-v"],
        ["docker", "compose", "-p", "osprey-small", "-f", mine, "down", "-v"],
        ["docker", "compose", "--project-name", "osprey-small", "-f", mine, "down", "-v"],
        ["docker", "compose", "down", "-v"],
        ["docker", "volume", "rm", "osprey-p5b-test_osprey-data", "osprey-small_osprey-data"],
        ["docker", "rm", "-v", "osprey-small-api-1"],
        ["docker", "rm", "-f", "osprey-test-g-pg"],
        ["docker", "rmi", "osprey/api:local"],
        ["docker", "image", "rm", "osprey/api:local"],
        ["docker", "volume", "prune", "-f"],
    ]
    for argv in refused:
        with pytest.raises(SystemExit, match="REFUSED"):
            driver.guarded(argv, home)


def test_a_refusal_in_teardown_never_stops_the_cleanup(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    driver = _driver()
    assert driver.guarded(["docker", "rmi", "osprey/api:local"], home, teardown=True) is None
    assert "REFUSED" in capsys.readouterr().out


def test_the_driver_removes_images_by_its_record_alone() -> None:
    """No removal by a difference of the machine's tags, and `rmi` only in the record's restore."""
    source = DRIVER.read_text(encoding="utf-8")
    assert not re.search(r"image_tags\(\)\s*-(?!>)|-\s*tags_before|\.keys\(\)\s*-", source)
    assert source.count('["docker", "rmi"') == 1  # sent once, by OwnImages's own untag
    assert "REFUSED: not to be run" not in source  # the owed proof's conditions are met
