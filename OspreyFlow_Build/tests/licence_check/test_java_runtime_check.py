"""`tools/java_runtime_check.py` (ADR-147 Amendment 2, ruling 1; the orchestrator's review of P5
round 3, item 2): `trivy image` does not see the Conduit's jlinked Temurin, so this check holds the
runtime to its declared version and to Temurin 21's newest. Each refusal planted in the shape its
input really takes: a Dockerfile `LABEL` line, `/opt/java/release` and `java -version` as the
built image gave them on the test server (`gates/p5_image_check.sh`; `jlink` writes no
`JAVA_RUNTIME_VERSION` there), and Adoptium's release names (rule 15)."""

from __future__ import annotations

import http.client
import json
import subprocess
import urllib.error
from pathlib import Path

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


@pytest.mark.parametrize(
    "label",
    [
        "LABEL org.ospreyflow.runtime.java.version=21.0.13+9",
        "LABEL a=x org.ospreyflow.runtime.java.version='21.0.13+9'",
        'LABEL a="x" \\\n      org.ospreyflow.runtime.java.version="21.0.13+9"',
        "LABEL org.ospreyflow.runtime.java.version 21.0.13+9",
    ],
)
def test_the_label_is_read_however_it_is_written(label: str) -> None:
    """As `licence-check` reads its labels (round 2's item 8: an anchored, double-quoted pattern
    passed four layouts silently)."""
    assert check.declared_version(f"FROM x AS java\n{label}\n") == "21.0.13+9"


def test_a_release_name_of_no_temurin_shape_is_refused_in_words() -> None:
    [problem] = problems(DOCKERFILE, None, ["jdk-21.0.13+9", "jdk-22-ea"])
    assert problem == "Adoptium named a release of no Temurin shape: 'jdk-22-ea'"


# `main` and `_latest` themselves, Adoptium's answer and the image read through their real code.


class _Answer:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, *_: object) -> bytes:
        return self.body


def _dockerfile(tmp_path: Path, version: str = "21.0.13+9") -> str:
    path = tmp_path / "Dockerfile"
    path.write_text(DOCKERFILE.replace("21.0.13+9", version))
    return str(path)


def _adoptium(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    sent: list[object] = []

    def urlopen(request: object, timeout: float) -> _Answer:
        sent.append(request)
        if isinstance(answer, BaseException):
            raise answer
        return _Answer(answer if isinstance(answer, bytes) else json.dumps(answer).encode())

    monkeypatch.setattr(check.urllib.request, "urlopen", urlopen)
    return sent


def test_main_passes_the_newest_and_sends_a_client_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent = _adoptium(monkeypatch, {"releases": ADOPTIUM})
    assert check.main(["--latest", "--dockerfile", _dockerfile(tmp_path)]) == 0
    assert "Temurin 21's newest" in capsys.readouterr().out
    assert sent[0].get_header("User-agent") == "ospreyflow-java-runtime-check"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "answer",
    [
        urllib.error.URLError("no route to host"),
        urllib.error.HTTPError(check.ADOPTIUM, 403, "Forbidden", {}, None),  # type: ignore[arg-type]
        http.client.IncompleteRead(b'{"releases": ["jdk-21'),
        b'{"releases": ["jdk-21',  # truncated
        {"releases": None},
        {"versions": ["jdk-21.0.13+9"]},
        {"releases": []},
    ],
    ids=["unreachable", "403", "incomplete", "truncated", "null", "another-key", "empty"],
)
def test_main_refuses_whenever_adoptium_cannot_be_read(
    answer: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed fetch is a refusal in words, never a pass and never a traceback."""
    _adoptium(monkeypatch, answer)
    assert check.main(["--latest", "--dockerfile", _dockerfile(tmp_path)]) == 1
    said = capsys.readouterr().err
    assert "Adoptium could not be read" in said or "Adoptium named no Temurin 21 release" in said


def test_main_refuses_an_old_pin_against_adoptium_s_real_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _adoptium(monkeypatch, {"releases": ADOPTIUM})
    assert check.main(["--latest", "--dockerfile", _dockerfile(tmp_path, "21.0.12.1+1")]) == 1
    assert "Temurin 21.0.13+9 is out" in capsys.readouterr().err


def _docker(monkeypatch: pytest.MonkeyPatch, version: str | None) -> None:
    """`docker run` as the image answers: its release file on `cat`, its banner on `java`."""
    release, banner = _release(version or "21.0.13+9")

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if version is None:
            raise subprocess.CalledProcessError(125, argv, stderr="Unable to find image")
        entry = argv[argv.index("--entrypoint") + 1]
        return subprocess.CompletedProcess(argv, 0, release if entry == "cat" else "", banner)

    monkeypatch.setattr(check.subprocess, "run", run)


def test_main_reads_the_image_and_refuses_one_that_drifted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _docker(monkeypatch, "21.0.13+9")
    assert check.main(["--image", "api:ci", "--dockerfile", _dockerfile(tmp_path)]) == 0
    _docker(monkeypatch, "21.0.1+12")
    assert check.main(["--image", "api:ci", "--dockerfile", _dockerfile(tmp_path)]) == 1
    assert "the image runs Java 21.0.1+12" in capsys.readouterr().err


def test_main_refuses_an_image_it_cannot_read_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _docker(monkeypatch, None)
    assert check.main(["--image", "api:ci", "--dockerfile", _dockerfile(tmp_path)]) == 1
    assert "the image's runtime could not be read" in capsys.readouterr().err
