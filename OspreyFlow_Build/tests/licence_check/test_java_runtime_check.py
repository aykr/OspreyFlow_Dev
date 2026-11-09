"""`tools/java_runtime_check.py` (ADR-147 Amendment 2, ruling 1; the orchestrator's review of P5
round 3, item 2): `trivy image` does not see the Conduit's jlinked Temurin, so this check holds the
runtime to its declared version and to Temurin 21's newest. Each refusal planted in the shape its
input really takes: a Dockerfile `LABEL` line, `/opt/java/release` and `java -version` as the
built image gave them on the test server (`gates/p5_image_check.sh`; `jlink` writes no
`JAVA_RUNTIME_VERSION` there), and Adoptium's release names (rule 15)."""

from __future__ import annotations

import pytest
from tools import java_runtime_check as check
from tools.java_runtime_check import problems, version_key

#: As the api Dockerfile writes it.
DOCKERFILE = (
    "FROM eclipse-temurin:21-jdk@sha256:" + "e" * 64 + " AS java\n"
    'LABEL org.ospreyflow.runtime.java.licence="GPL-2.0-only WITH Classpath-exception-2.0"\n'
    'LABEL org.ospreyflow.runtime.java.version="21.0.13+9"\n'
)


def _release(version: str) -> tuple[str, str]:
    """The image's `/opt/java/release` and `java -version`, as the test server's build gave them."""
    plain = version.split("+")[0]
    return (
        f'JAVA_VERSION="{plain}"\nMODULES="java.base java.compiler java.datatransfer java.xml"\n',
        f'openjdk version "{plain}" 2026-08-18 LTS\n'
        f"OpenJDK Runtime Environment Temurin-{version} (build {version}-LTS)\n"
        f"OpenJDK 64-Bit Server VM Temurin-{version} (build {version}-LTS, mixed mode)\n",
    )


#: Adoptium's answer of 9 November 2026, newest first.
ADOPTIUM = ["jdk-21.0.13+9", "jdk-21.0.12.1+1", "jdk-21.0.12+8", "jdk-21.0.11+10"]


def test_the_runtime_declared_built_and_newest_passes() -> None:
    assert problems(DOCKERFILE, _release("21.0.13+9"), ADOPTIUM) == []


def test_a_quarterly_update_not_taken_is_refused() -> None:
    """The case trivy cannot see: the image is what it declares, and Temurin has moved on."""
    pinned = DOCKERFILE.replace("21.0.13+9", "21.0.12.1+1")
    [problem] = problems(pinned, _release("21.0.12.1+1"), ADOPTIUM)
    assert "Temurin 21.0.13+9 is out and the image pins 21.0.12.1+1" in problem


def test_a_label_that_drifted_from_the_digest_is_refused() -> None:
    assert problems(DOCKERFILE, _release("21.0.12.1+1"), ADOPTIUM) == [
        "the image's /opt/java/release names 21.0.12.1, its Dockerfile 21.0.13+9",
        "the image runs Java 21.0.12.1+1, its Dockerfile declares 21.0.13+9",
    ]


def test_a_rebuild_of_the_same_version_is_told_apart_by_its_build() -> None:
    """`/opt/java/release` names no build: a `+8` image under a `+9` label is `java -version`'s."""
    [problem] = problems(DOCKERFILE, _release("21.0.13+8"), ADOPTIUM)
    assert problem == "the image runs Java 21.0.13+8, its Dockerfile declares 21.0.13+9"


def test_a_dockerfile_without_the_label_or_with_two_is_refused() -> None:
    bare = DOCKERFILE.replace('LABEL org.ospreyflow.runtime.java.version="21.0.13+9"\n', "")
    assert problems(bare, None, None) == [
        "the api Dockerfile declares no single org.ospreyflow.runtime.java.version label"
    ]
    twice = DOCKERFILE + 'LABEL org.ospreyflow.runtime.java.version="21.0.12+8"\n'
    assert problems(twice, None, None) != []


def test_a_label_of_no_temurin_shape_is_refused() -> None:
    [problem] = problems(DOCKERFILE.replace("21.0.13+9", "latest"), None, None)
    assert "not a Temurin version" in problem


def test_a_runtime_naming_no_version_is_refused() -> None:
    release, java_version = _release("21.0.13+9")
    [problem] = problems(DOCKERFILE, ('MODULES="java.base"\n', java_version), None)
    assert "/opt/java/release names no single JAVA_VERSION" in problem
    [problem] = problems(DOCKERFILE, (release, 'openjdk version "21.0.13"\n'), None)
    assert "java -version names no single build" in problem


def test_an_empty_answer_from_adoptium_is_refused_never_passed() -> None:
    assert problems(DOCKERFILE, None, []) == ["Adoptium named no Temurin 21 release"]


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("21.0.12+8", "21.0.12.1+1"),  # a point release over its quarter
        ("21.0.9+10", "21.0.10+7"),  # 10 after 9, never as text
        ("21.0.13+8", "21.0.13+9"),  # a rebuild
        ("jdk-21.0.12.1+1", "21.0.13+9-LTS"),  # the release name's and the runtime's spellings
    ],
)
def test_versions_are_ordered_as_temurin_numbers_them(older: str, newer: str) -> None:
    assert version_key(older) < version_key(newer)


def test_the_api_dockerfile_declares_its_runtime_s_version() -> None:
    """The real Dockerfile, offline: its label is there and of Temurin's shape."""
    assert problems(check.DOCKERFILE.read_text(), None, None) == []
