"""What the Conduit's image carries for the tier-1 basemap build (`06_DECISIONS.md` ADR-147
Amendment 2; the owner's ruling 1 of 9 November 2026, option A): **a Java 21 runtime**, Eclipse
Temurin under GPL-2.0 with the Classpath exception (the licence register's recorded runtime
exception, `spec/00_ARCHITECTURE.md` §7), jlinked from the official image **pinned by digest**, and
declared by the label `make licence-check` reads (`tests/licence_check/test_runtime_licences.py`).
The maps file's folder is made for the Conduit's user."""

from __future__ import annotations

import re

from tools.layout import CORE
from tools.licence_check import _instructions

DOCKERFILE = (CORE / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")


def test_the_image_carries_a_jlinked_java_pinned_by_digest_and_declared() -> None:
    assert re.search(r"^FROM eclipse-temurin:21-jdk@sha256:[0-9a-f]{64} AS java$", DOCKERFILE, re.M)
    assert re.search(r"^RUN jlink\b", DOCKERFILE, re.M)
    # By default (ADR-148 decision 12): the jlinked stage is the one the image copies from.
    assert re.search(r"^ARG CONDUIT_JAVA=included$", DOCKERFILE, re.M)
    assert "COPY --from=java /opt/jre /opt/java" in _stage("runtime-included")
    assert 'LABEL org.ospreyflow.runtime.java.licence="GPL-2.0-only WITH Classpath-exception-2.0"' in (
        DOCKERFILE
    )
    # On the path the Conduit's `shutil.which("java")` reads (`map_admin.MapAdmin.basemap`).
    assert re.search(r'^ENV PATH="[^"]*/opt/java/bin', DOCKERFILE, re.M)
    # No other Java stage, unpinned or otherwise.
    assert len(re.findall(r"^FROM .*(temurin|openjdk|jdk|jre)", DOCKERFILE, re.M | re.I)) == 1


def test_the_maps_file_s_folder_is_made_for_the_conduit_s_user() -> None:
    assert (
        "mkdir -p /run/osprey/map-settings && chown osprey:osprey /run/osprey/map-settings"
        in DOCKERFILE
    )


def _stage(name: str) -> str:
    """The instructions of the stage `name`, up to the next `FROM`."""
    return DOCKERFILE.split(f"\nFROM python:3.12-slim AS {name}\n", 1)[1].split("\nFROM ", 1)[0]


def _final() -> str:
    return DOCKERFILE.rsplit("\nFROM ", 1)[1]


def test_the_cloud_platform_s_build_carries_no_java() -> None:
    """ADR-148 decision 12: the build argument chooses the final stage's base, and the base it
    chooses for `CONDUIT_JAVA=omitted` is the plain Python image with no stage of Java's under it,
    so the runtime and its stage are never in that image."""
    assert _final().splitlines()[0] == "runtime-${CONDUIT_JAVA}"
    assert set(re.findall(r"^FROM (\S+) AS runtime-(?:included|omitted)$", DOCKERFILE, re.M)) == {
        "python:3.12-slim"
    }
    # No stage left over from an earlier shape (a `java-omitted` copying an empty folder).
    assert re.findall(r"^FROM \S+ AS (\S+)$", DOCKERFILE, re.M) == [
        "builder", "java", "runtime-included", "runtime-omitted"
    ]  # fmt: skip


def test_the_omitted_image_does_not_declare_java() -> None:
    """The independent review of P7, item 9: the build without Java is not labelled with Java's
    licence or version, has no JAVA_HOME and no Java on its path; only the base that copies the
    runtime declares it, and the build argument chooses between the two (the build itself, run
    once: `process/lanes/platform/gates/p7_conduit_no_java.sh`)."""
    included, omitted = _stage("runtime-included"), _stage("runtime-omitted")
    for declared in ("runtime.java.licence", "runtime.java.version", "JAVA_HOME", "/opt/java/bin"):
        assert declared in included, declared
        assert declared not in omitted, declared
    assert omitted.strip() == 'LABEL org.ospreyflow.runtime.java.included="omitted"'
    assert 'LABEL org.ospreyflow.runtime.java.included="included"' in included
    # The final stage's instructions after its base, as Docker reads them (comments left out): none
    # names Java.
    after_its_base = _instructions(_final())[1:]
    assert not [i for i in after_its_base if "java" in i.lower()], "Java in the final stage"


def test_the_final_stage_upgrades_before_the_code_and_as_root() -> None:
    """The round-2 review of P7, item 5: the Debian upgrade is the final stage's first instruction
    (`tests/test_images_built_fresh.py` needs it in that stage), run as the image's root before any
    code layer, so a code change does not repeat it and no `USER root` is needed after the Conduit's
    user is set; the user is set once, last."""
    instructions = _instructions(_final())
    assert instructions[1].startswith("RUN apt-get update && apt-get upgrade -y"), instructions[1]
    first_copy = next(n for n, i in enumerate(instructions) if i.startswith("COPY"))
    assert 1 < first_copy
    users = [i for i in instructions if i.startswith("USER")]
    assert users == ["USER 10001:10001"]
