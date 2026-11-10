"""P5b's live driver (`process/lanes/platform-b/gates/p5b_live_update.py`) removes only the image
tags it made, by the names it recorded when it made them. On 10 November 2026 its first cleanup
removed "every tag new since the start" and deleted three images another lane built on the shared
server while it ran. The fake `docker` here keeps a real tag table: another lane tags an image in
the middle of the run, and that tag must survive the driver's teardown (rule 15: the fake refuses
what docker refuses — `rmi` of a name it does not hold)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

DRIVER = (
    Path(__file__).resolve().parents[1] / "process/lanes/platform-b/gates/p5b_live_update.py"
)


def _driver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("p5b_live_update", DRIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDocker:
    """`docker tag` and `docker rmi` over a table of tags; `rmi` of an unknown tag fails, as
    docker's does."""

    def __init__(self, tags: set[str]) -> None:
        self.tags = set(tags)
        self.removed: list[str] = []

    def __call__(self, argv: Sequence[str], check: bool = False, **_: Any) -> Any:
        verb, *rest = list(argv)[1:]
        if verb == "tag":
            self.tags.add(rest[1])
        elif verb == "rmi":
            unknown = [t for t in rest if t not in self.tags]
            if unknown and check:
                raise subprocess.CalledProcessError(1, argv)
            for name in rest:
                self.tags.discard(name)
                self.removed.append(name)
        return subprocess.CompletedProcess(argv, 0)


def test_the_teardown_leaves_a_tag_another_lane_made_while_the_run_was_going() -> None:
    driver = _driver()
    docker = FakeDocker({"osprey-small/workspace@sha256:abc", "python:3.12-slim"})
    own = driver.OwnTags(runner=docker)

    own.tag("sha256:abc", "osprey/workspace:local", existed=False)
    # Mid-run: another lane builds on the same server.
    docker.tags.add("localhost:5001/ospreyflow/api:9fa5b19a")
    own.built("osprey/api:local", existed=False)
    docker.tags.add("osprey/api:local")
    # A tag that was there before the run is never the run's to remove.
    own.built("python:3.12-slim", existed=True)

    assert own.remove() == ["osprey/workspace:local", "osprey/api:local"]
    assert docker.removed == ["osprey/workspace:local", "osprey/api:local"]
    assert "localhost:5001/ospreyflow/api:9fa5b19a" in docker.tags
    assert "python:3.12-slim" in docker.tags


def test_the_driver_never_removes_by_a_difference_of_the_machines_tags() -> None:
    """The cleanup's only removal is `OwnTags.remove`, so a later edit that brings back
    `image_tags() - tags_before` is caught here, not on a shared server."""
    source = DRIVER.read_text(encoding="utf-8")
    assert not re.search(r"image_tags\(\)\s*-(?!>)|-\s*tags_before", source)
    assert source.count('"rmi"') == 1


@pytest.mark.parametrize("existed", [True, False])
def test_a_tag_is_recorded_only_when_the_run_made_it(existed: bool) -> None:
    driver = _driver()
    docker = FakeDocker({"osprey/ner:local"} if existed else set())
    own = driver.OwnTags(runner=docker)
    own.built("osprey/ner:local", existed=existed)
    assert own.remove() == ([] if existed else ["osprey/ner:local"])
