"""`tools/java_runtime_check.py` (ADR-147 Amendment 2, ruling 1): `trivy image` does not see the
Conduit's jlinked Temurin, so this check holds the runtime to its declared version and its pin to
the digest its tag resolves to on Docker Hub now (the orchestrator's call, over Adoptium's release
list). Each refusal is planted in the shape its input really takes (rule 15):

- a Dockerfile's `FROM … AS java` and `LABEL` lines;
- `/opt/java/release` and `java -version`, as the built image gave them on the test server
  (`gates/p5_image_check.sh`; `jlink` writes no `JAVA_RUNTIME_VERSION` there);
- Docker Hub's answer for a tag (`{"name", "digest", "images", …}`, the index's digest), with the
  real digests of `21-jdk` at 21.0.12.1+1 and at 21.0.13+9."""

from __future__ import annotations

import http.client
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest
from tools import java_runtime_check as check
from tools.java_runtime_check import problems, version_key

#: `eclipse-temurin:21-jdk`'s index digest at 21.0.13+9 (29 October 2026), and before, at
#: 21.0.12.1+1.
NOW = "sha256:ebfbb18d11ff163ee83b21258acf12248af48d22a0fdfdc68fa1a1516c05976a"
BEFORE = "sha256:f9bf7e9fe2f9bc4657537c1a7e20c768f0c3bafca41598263be4714783dd62eb"

#: As the api Dockerfile writes it.
DOCKERFILE = (
    "FROM python:3.12-slim AS builder\n"
    f"FROM eclipse-temurin:21-jdk@{NOW} AS java\n"
    "RUN jlink --add-modules java.base --output /opt/jre\n"
    'LABEL org.ospreyflow.runtime.java.licence="GPL-2.0-only WITH Classpath-exception-2.0"\n'
    'LABEL org.ospreyflow.runtime.java.version="21.0.13+9"\n'
)
OLD_PIN = DOCKERFILE.replace(NOW, BEFORE).replace("21.0.13+9", "21.0.12.1+1")


def _release(version: str) -> tuple[str, str]:
    """The image's `/opt/java/release` and `java -version`, as the test server's build gave them."""
    plain = version.split("+")[0]
    return (
        f'JAVA_VERSION="{plain}"\nMODULES="java.base java.compiler java.datatransfer java.xml"\n',
        f'openjdk version "{plain}" 2026-08-18 LTS\n'
        f"OpenJDK Runtime Environment Temurin-{version} (build {version}-LTS)\n"
        f"OpenJDK 64-Bit Server VM Temurin-{version} (build {version}-LTS, mixed mode)\n",
    )


def test_the_runtime_declared_built_and_pinned_at_its_tag_passes() -> None:
    assert problems(DOCKERFILE, _release("21.0.13+9"), NOW) == []


def test_a_pin_its_tag_has_moved_on_from_is_refused() -> None:
    """The case trivy cannot see: the image is what it declares, and the tag now names another."""
    [problem] = problems(OLD_PIN, _release("21.0.12.1+1"), NOW)
    assert problem == (
        f"eclipse-temurin:21-jdk now resolves to {NOW} and the image pins {BEFORE}: "
        "repin the api Dockerfile's java stage by digest and its label"
    )


def test_a_label_that_drifted_from_the_digest_is_refused() -> None:
    assert problems(DOCKERFILE, _release("21.0.12.1+1"), NOW) == [
        "the image's /opt/java/release names 21.0.12.1, its Dockerfile 21.0.13+9",
        "the image runs Java 21.0.12.1+1, its Dockerfile declares 21.0.13+9",
    ]


def test_a_rebuild_of_the_same_version_is_told_apart_by_its_build() -> None:
    """`/opt/java/release` names no build: a `+8` image under a `+9` label is `java -version`'s."""
    [problem] = problems(DOCKERFILE, _release("21.0.13+8"), NOW)
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


@pytest.mark.parametrize(
    "stage",
    [
        "FROM eclipse-temurin:21-jdk AS java",  # by tag alone: nothing pinned to compare
        f"FROM eclipse-temurin@{NOW} AS java",  # by digest alone: no tag to ask after
        f"FROM eclipse-temurin:21-jdk@{NOW} AS jre",  # not the Java stage
    ],
)
def test_a_java_stage_not_pinned_by_tag_and_digest_is_refused(stage: str) -> None:
    dockerfile = DOCKERFILE.replace(f"FROM eclipse-temurin:21-jdk@{NOW} AS java", stage)
    assert problems(dockerfile, None, NOW) == [
        "the api Dockerfile has no single Java stage pinned by digest"
    ]


@pytest.mark.parametrize("answer", ["", "latest", "sha256:abc", NOW.upper()])
def test_an_answer_naming_no_digest_is_refused_never_passed(answer: str) -> None:
    [problem] = problems(DOCKERFILE, None, answer)
    assert problem.startswith("Docker Hub named no digest for eclipse-temurin:21-jdk")


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


def test_the_api_dockerfile_declares_its_runtime_and_pins_its_java_stage() -> None:
    """The real Dockerfile, offline: its label is there and of Temurin's shape, and its Java stage
    is one official tag pinned by digest."""
    real = check.DOCKERFILE.read_text()
    assert problems(real, None, None) == []
    assert check.java_stage(real) is not None


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


# `main` and `_current` themselves: Docker Hub's answer and the image read through their real code.


class _Answer:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, *_: object) -> bytes:
        return self.body


def _dockerfile(tmp_path: Path, text: str = DOCKERFILE) -> str:
    path = tmp_path / "Dockerfile"
    path.write_text(text)
    return str(path)


def _hub(digest: object) -> dict[str, object]:
    """Docker Hub's answer for a tag, in the shape it answers (fields as on 9 November 2026)."""
    return {
        "name": "21-jdk", "digest": digest, "last_updated": "2026-10-29T20:00:40.470353Z",
        "images": [{"architecture": "amd64", "digest": "sha256:" + "0" * 64}],
    }  # fmt: skip


def _docker_hub(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
    sent: list[object] = []

    def urlopen(request: object, timeout: float) -> _Answer:
        sent.append(request)
        if isinstance(answer, BaseException):
            raise answer
        return _Answer(answer if isinstance(answer, bytes) else json.dumps(answer).encode())

    monkeypatch.setattr(check.urllib.request, "urlopen", urlopen)
    return sent


def test_main_passes_a_current_pin_asking_after_the_dockerfile_s_own_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent = _docker_hub(monkeypatch, _hub(NOW))
    assert check.main(["--current", "--dockerfile", _dockerfile(tmp_path)]) == 0
    assert "pinned at its tag's current digest" in capsys.readouterr().out
    [request] = sent
    assert request.full_url == (  # type: ignore[attr-defined]
        "https://hub.docker.com/v2/repositories/library/eclipse-temurin/tags/21-jdk"
    )
    agent = request.get_header("User-agent")  # type: ignore[attr-defined]
    assert agent == "ospreyflow-java-runtime-check"


def test_main_refuses_a_pin_its_tag_has_moved_on_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _docker_hub(monkeypatch, _hub(NOW))
    assert check.main(["--current", "--dockerfile", _dockerfile(tmp_path, OLD_PIN)]) == 1
    assert f"now resolves to {NOW} and the image pins {BEFORE}" in capsys.readouterr().err


@pytest.mark.parametrize(
    "answer",
    [
        urllib.error.URLError("no route to host"),
        urllib.error.HTTPError(check.HUB_TAG, 429, "Too Many Requests", {}, None),  # type: ignore[arg-type]
        http.client.IncompleteRead(b'{"digest": "sha256:'),
        b'{"digest": "sha256:',  # truncated
        _hub(None),
        {"name": "21-jdk"},
        _hub(""),
    ],
    ids=["unreachable", "429", "incomplete", "truncated", "null", "no-digest", "empty"],
)
def test_main_refuses_whenever_docker_hub_cannot_be_read(
    answer: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed fetch is a refusal in words, never a pass and never a traceback."""
    _docker_hub(monkeypatch, answer)
    assert check.main(["--current", "--dockerfile", _dockerfile(tmp_path)]) == 1
    said = capsys.readouterr().err
    assert "Docker Hub could not be read" in said or "Docker Hub named no digest" in said


def test_main_refuses_a_java_stage_it_cannot_ask_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent = _docker_hub(monkeypatch, _hub(NOW))
    unpinned = DOCKERFILE.replace(f"@{NOW}", "")
    assert check.main(["--current", "--dockerfile", _dockerfile(tmp_path, unpinned)]) == 1
    assert "no single Java stage pinned by digest" in capsys.readouterr().err
    assert sent == []


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
    """CI's step (`P5_ci.diff`): `--image` alone, over the image the job has just built."""
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
