"""`make licence-check`'s image leg (`spec/00_ARCHITECTURE.md` §7, ADR-147 Amendment 2; the owner's
ruling 1 of 9 November 2026): a runtime copied into an image is declared by a label in its Dockerfile,
and its licence passes only as the allowlist passes one, or as the one recorded exception: a Java
runtime under `GPL-2.0-only WITH Classpath-exception-2.0`.

Every violation is planted as the leg reads it at its real call site, a Dockerfile's text (rule 15):
a plain GPL-2.0 Java, a GPL-3.0 with the exception, GPL-2.0 with another exception, the exception for
a runtime not recorded, AGPL, and a Java stage that declares nothing. Each is refused, and the real
Dockerfiles pass.
"""

from __future__ import annotations

import pytest

from tools.licence_check import find_runtime_offenders, runtime_allowed


def _dockerfile(licence: str | None, runtime: str = "java") -> str:
    label = f'LABEL org.ospreyflow.runtime.{runtime}.licence="{licence}"\n' if licence else ""
    return (
        "FROM eclipse-temurin:21-jdk@sha256:" + "0" * 64 + " AS java\n"
        "RUN jlink --add-modules java.base --output /opt/java\n"
        "FROM python:3.12-slim\n"
        "COPY --from=java /opt/java /opt/java\n" + label
    )


def test_the_recorded_classpath_exception_passes_for_java() -> None:
    assert find_runtime_offenders({"api": _dockerfile("GPL-2.0-only WITH Classpath-exception-2.0")}) == []
    assert runtime_allowed("GPL-2.0 WITH Classpath-exception-2.0", "java")


@pytest.mark.parametrize(
    "licence",
    [
        "GPL-2.0-only",  # a plain GPL-2.0 Java: still refused
        "GPL-2.0",
        "GPL-3.0-only WITH Classpath-exception-2.0",
        "GPL-2.0-only WITH GCC-exception-3.1",
        "AGPL-3.0-only",
        "GPL-2.0-only WITH Classpath-exception-2.0 AND GPL-3.0",
    ],
)
def test_any_other_gpl_java_is_refused(licence: str) -> None:
    assert find_runtime_offenders({"api": _dockerfile(licence)}) == [("api", "java", licence)]


def test_the_exception_is_for_the_recorded_runtime_alone() -> None:
    planted = _dockerfile("GPL-2.0-only WITH Classpath-exception-2.0", runtime="other-vm")
    assert ("api", "other-vm", "GPL-2.0-only WITH Classpath-exception-2.0") in (
        find_runtime_offenders({"api": planted})
    )


@pytest.mark.parametrize(
    "carries",
    [
        "FROM eclipse-temurin:21-jre AS java",
        "RUN jlink --add-modules java.base --output /opt/jre",
        "COPY --from=other /opt/java /opt/java",
        "RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless",
        "RUN apt-get install -y default-jre",
        "RUN apk add --no-cache openjdk21",
    ],
)
def test_a_java_runtime_the_image_does_not_declare_is_refused(carries: str) -> None:
    """Each way a Java gets into an image, alone (rule 15: a plant carrying all of them at once
    would stay red with any one of them undetected)."""
    planted = f"FROM python:3.12-slim\n{carries}\n"
    assert find_runtime_offenders({"api": planted}) == [("api", "java", "undeclared")]


def test_an_image_with_no_java_is_not_flagged() -> None:
    planted = "FROM python:3.12-slim\nRUN apt-get install -y git\nCOPY scripts ./scripts\n"
    assert find_runtime_offenders({"api": planted}) == []


def test_a_permissive_runtime_passes_as_the_allowlist_does() -> None:
    planted = 'FROM python:3.12-slim\nLABEL org.ospreyflow.runtime.tool.licence="Apache-2.0"\n'
    assert find_runtime_offenders({"x": planted}) == []


def test_the_real_dockerfiles_pass_and_the_conduit_declares_its_java() -> None:
    from tools.layout import CORE

    assert find_runtime_offenders() == []
    conduit = (CORE / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert 'org.ospreyflow.runtime.java.licence="GPL-2.0-only WITH Classpath-exception-2.0"' in conduit
