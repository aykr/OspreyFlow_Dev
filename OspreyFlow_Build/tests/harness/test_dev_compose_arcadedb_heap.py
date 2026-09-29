"""`deploy/compose/dev.yaml` and the renderer must give ArcadeDB the same heap — one source.

**The drift this exists to stop already happened once, and cost two rounds.**
`harness/render.py`'s own ArcadeDB comment records it: `dev.yaml` measured the problem and raised
its heap to `-Xms1G -Xmx6G` in Phase 5, "the renderer did not carry it over, so a rendered
deployment was strictly worse-configured than the dev stack it replaces, on a value this
repository had already paid to learn." The renderer was then corrected by hand — and the two
literals went straight back to being two literals, with nothing asserting they agreed.

Round 13bb raised both, from the profile's own memory floor rather than by hand
(`harness/profiles.py` has the OOM that forced it). This file is what keeps them together: the
developer stack and every rendered deployment configure the same server the same way, or this
fails by name.

**Why a test and not a generated file.** `deploy/compose/dev.yaml` is hand-maintained and heavily
commented — nearly a hundred lines of measured incident history live in its ArcadeDB stanza, which
is the most valuable thing in it. Generating it would throw that away (round 13b watched
`build_local_basemap` do exactly that to `osprey.yaml`). A gate keeps the comments and the
agreement both.
"""

from __future__ import annotations

import re

from harness.profiles import arcadedb_java_memory_opts

from tools.layout import REPO as REPO_ROOT

DEV_COMPOSE = REPO_ROOT / "deploy" / "compose" / "dev.yaml"

_SETTING = re.compile(r'^\s*ARCADEDB_OPTS_MEMORY:\s*"([^"]*)"\s*$', re.MULTILINE)


def dev_compose_arcadedb_memory_opts(source: str) -> str:
    """Extracted with a regex rather than a YAML parse, deliberately: a parse would silently
    accept the key moving to another service, and the thing being asserted is the literal a
    reader sees on that one line."""
    found = _SETTING.findall(source)
    assert len(found) == 1, (
        f"expected exactly one ARCADEDB_OPTS_MEMORY line in {DEV_COMPOSE.name}, found {found}"
    )
    return str(found[0])


def test_the_dev_stack_and_the_renderer_give_arcadedb_the_same_heap() -> None:
    assert dev_compose_arcadedb_memory_opts(DEV_COMPOSE.read_text(encoding="utf-8")) == (
        arcadedb_java_memory_opts()
    ), (
        "deploy/compose/dev.yaml and harness/profiles.py disagree about ArcadeDB's heap. They are "
        "one setting for one server; a developer's stack and a rendered deployment must not be "
        "configured differently on a value this repository has already paid twice to learn."
    )


def test_the_heap_is_derived_from_the_profile_floor_not_a_literal() -> None:
    """The gate above would still pass if someone replaced the derivation with a hand-written
    literal that happened to match today. This is the half that would not — per `CLAUDE.md`
    rule 15, the planted violation has to take the shape the defect actually takes, and the
    defect here is a number that stops moving with the floor it came from."""
    from harness import profiles

    doubled_floor = {name: size * 2 for name, size in profiles.PROFILE_FLOORS.items()}
    original = profiles.PROFILE_FLOORS
    try:
        profiles.PROFILE_FLOORS = doubled_floor  # type: ignore[assignment]
        assert profiles.arcadedb_heap_gib() == 16, (
            "doubling the profile floor did not double the heap — the heap is no longer derived "
            "from the floor, whatever the arithmetic in `arcadedb_heap_gib` currently reads as"
        )
    finally:
        profiles.PROFILE_FLOORS = original  # type: ignore[assignment]


def test_the_server_is_told_to_exit_on_a_heap_oom() -> None:
    """Round 13bb's second finding, asserted rather than left in a comment: measured directly,
    ArcadeDB's readiness endpoint answered `204` and `docker inspect` reported `healthy` after a
    fatal `java.lang.OutOfMemoryError` had killed both open databases' transaction managers. The
    healthcheck cannot see a heap OOM, so the JVM has to stop pretending it survived one."""
    assert "-XX:+ExitOnOutOfMemoryError" in arcadedb_java_memory_opts()
    assert "-XX:+ExitOnOutOfMemoryError" in dev_compose_arcadedb_memory_opts(
        DEV_COMPOSE.read_text(encoding="utf-8")
    )
