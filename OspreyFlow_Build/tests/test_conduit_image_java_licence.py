"""What the Conduit's image carries for the tier-1 basemap build (`06_DECISIONS.md` ADR-147
Amendment 2; the owner's ruling 1 of 9 November 2026, option A): **a Java 21 runtime**, Eclipse
Temurin under GPL-2.0 with the Classpath exception (the licence register's recorded runtime
exception, `spec/00_ARCHITECTURE.md` §7), jlinked from the official image **pinned by digest**, and
declared by the label `make licence-check` reads (`tests/licence_check/test_runtime_licences.py`).
The maps file's folder is made for the Conduit's user."""

from __future__ import annotations

import re

from tools.layout import CORE

DOCKERFILE = (CORE / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")


def test_the_image_carries_a_jlinked_java_pinned_by_digest_and_declared() -> None:
    assert re.search(r"^FROM eclipse-temurin:21-jdk@sha256:[0-9a-f]{64} AS java$", DOCKERFILE, re.M)
    assert re.search(r"^RUN jlink\b", DOCKERFILE, re.M)
    # By default (ADR-148 decision 12): the jlinked stage is the one the image copies from.
    assert re.search(r"^ARG CONDUIT_JAVA=included$", DOCKERFILE, re.M)
    assert re.search(r"^FROM java AS java-included$", DOCKERFILE, re.M)
    assert re.search(r"^FROM java-\$\{CONDUIT_JAVA\} AS java-chosen$", DOCKERFILE, re.M)
    assert "COPY --from=java-chosen /opt/jre /opt/java" in DOCKERFILE
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


def test_the_cloud_platform_s_build_carries_no_java() -> None:
    """ADR-148 decision 12: `CONDUIT_JAVA=omitted` copies an empty folder from a stage that is not
    Java's, so the runtime and its stage are never in that image, and the image says which."""
    omitted = DOCKERFILE.split("FROM python:3.12-slim AS java-omitted", 1)[1].split("\nFROM ", 1)[0]
    assert omitted.strip() == "RUN mkdir -p /opt/jre"
    assert 'LABEL org.ospreyflow.runtime.java.included="${CONDUIT_JAVA}"' in DOCKERFILE
    # The only stages are the default's and the omission's.
    assert set(re.findall(r"^FROM (\S+) AS java-(?:included|omitted)$", DOCKERFILE, re.M)) == {
        "java", "python:3.12-slim"
    }
