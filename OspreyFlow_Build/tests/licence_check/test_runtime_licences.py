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
from tools import licence_check
from tools.licence_check import (
    find_runtime_offenders,
    find_runtimes_awaiting_owner,
    runtime_allowed,
)


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
    planted = "FROM python:3.12-slim\nRUN apt-get install -y curl\nCOPY scripts ./scripts\n"
    assert find_runtime_offenders({"api": planted}) == []


def test_a_permissive_runtime_passes_as_the_allowlist_does() -> None:
    planted = 'FROM python:3.12-slim\nLABEL org.ospreyflow.runtime.tool.licence="Apache-2.0"\n'
    assert find_runtime_offenders({"x": planted}) == []


def test_the_real_dockerfiles_pass_and_the_conduit_declares_its_java() -> None:
    from tools.layout import CORE

    assert find_runtime_offenders() == []
    conduit = (CORE / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert 'org.ospreyflow.runtime.java.licence="GPL-2.0-only WITH Classpath-exception-2.0"' in conduit


@pytest.mark.parametrize(
    "label",
    [
        "LABEL org.ospreyflow.runtime.node.licence='GPL-3.0-only'",
        "LABEL org.ospreyflow.runtime.node.licence=GPL-3.0-only",
        'LABEL maintainer="x" org.ospreyflow.runtime.node.licence="GPL-3.0-only" version=1',
        'LABEL maintainer="x" \\\n      org.ospreyflow.runtime.node.licence="GPL-3.0-only"',
        "LABEL org.ospreyflow.runtime.node.licence GPL-3.0-only",
        'label org.ospreyflow.runtime.node.licence="GPL-3.0-only"',
    ],
    ids=["single-quoted", "unquoted", "among-others", "continued", "legacy-form", "lower-case"],
)
def test_a_declared_runtime_is_read_however_its_label_is_written(label: str) -> None:
    """The orchestrator's review of P5, item 8: a label the leg could not read passed silently."""
    planted = f"FROM node:22-slim\n{label}\n"
    assert find_runtime_offenders({"x": planted}) == [("x", "node", "GPL-3.0-only")]


GIT = "FROM python:3.12-slim\nRUN apt-get update && apt-get install -y --no-install-recommends \\\n    git curl\n"


def test_git_installed_and_undeclared_is_refused() -> None:
    assert find_runtime_offenders({"api": GIT}) == [("api", "git", "undeclared")]
    # `git-lfs` brings `git` with it, so it is `git` too.
    assert find_runtime_offenders({"api": GIT.replace("git curl", "git-lfs curl")}) == [
        ("api", "git", "undeclared")
    ]
    assert find_runtime_offenders({"api": GIT.replace("git curl", "git-core curl")}) == [
        ("api", "git", "undeclared")
    ]
    copied = "FROM python:3.12-slim\nCOPY --from=tools /usr/bin/git /usr/bin/git\n"
    assert find_runtime_offenders({"api": copied}) == [("api", "git", "undeclared")]
    assert find_runtime_offenders({"api": GIT.replace("git curl", "gitk-viewer curl")}) == []


CONDUIT = "services/api/Dockerfile"


def _real_conduit() -> str:
    return (licence_check.CORE / CONDUIT).read_text(encoding="utf-8")


def test_a_runtime_put_to_the_owner_is_named_as_awaiting_never_passed_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The awaiting mechanism itself (kept for a later ruling, though nothing awaits now): an
    entry names its runtime on every run instead of failing it, pinned to that image and licence;
    without the entry it is an offender like any GPL runtime."""
    declared = GIT + 'LABEL org.ospreyflow.runtime.git.licence="GPL-2.0-only"\n'
    monkeypatch.setattr(
        licence_check, "AWAITING_OWNER", {(CONDUIT, "git", "GPL-2.0-only"): "a ruling awaited"}
    )
    assert find_runtime_offenders({CONDUIT: declared}) == []
    assert find_runtimes_awaiting_owner({CONDUIT: declared}) == [(CONDUIT, "git", "GPL-2.0-only")]
    # Pinned: in another image, or under another licence, it is an offender as usual.
    assert find_runtime_offenders({"other": declared}) == [("other", "git", "GPL-2.0-only")]
    agpl = declared.replace("GPL-2.0-only", "AGPL-3.0-only")
    assert find_runtime_offenders({CONDUIT: agpl}) == [(CONDUIT, "git", "AGPL-3.0-only")]
    monkeypatch.setattr(licence_check, "AWAITING_OWNER", {})
    assert find_runtime_offenders({CONDUIT: declared}) == [(CONDUIT, "git", "GPL-2.0-only")]


def test_the_conduit_carries_no_git_and_nothing_awaits_the_owner() -> None:
    """The owner's ruling of 9 November 2026 carried out (L1.7a): the Conduit commits with dulwich,
    so its image installs no `git`, declares none, and the gate admits it under no entry. The pass
    is git absent and nothing awaiting."""
    assert licence_check.AWAITING_OWNER == {}
    assert find_runtimes_awaiting_owner() == []
    conduit = _real_conduit()
    assert "git" not in licence_check.declared_runtimes(conduit)
    assert (
        licence_check._GIT_IN_IMAGE.search("\n".join(licence_check._instructions(conduit))) is None
    )
    assert find_runtime_offenders() == []


@pytest.mark.parametrize(
    "plant",
    [
        "RUN apt-get update && apt-get install -y --no-install-recommends git \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n",
        "RUN apt-get update && apt-get install -y --no-install-recommends git \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n"
        'LABEL org.ospreyflow.runtime.git.licence="GPL-2.0-only"\n',
    ],
    ids=["installed", "installed-and-declared"],
)
def test_git_planted_in_the_real_conduit_dockerfile_is_an_offender(plant: str) -> None:
    """Rule 15, at the gate's real call site: `git` put back into the Conduit's own Dockerfile
    text, after its Java runtime is copied in, is named, whether or not it is declared."""
    conduit = _real_conduit()
    anchor = "COPY --from=java /opt/jre /opt/java\n"
    assert conduit.count(anchor) == 1
    planted = conduit.replace(anchor, plant + anchor)
    expected = "undeclared" if "LABEL" not in plant else "GPL-2.0-only"
    assert find_runtime_offenders({CONDUIT: planted}) == [(CONDUIT, "git", expected)]
    assert find_runtimes_awaiting_owner({CONDUIT: planted}) == []


def test_every_run_says_nothing_awaits_the_owner(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` over the real tree: nothing named as not yet passed, and its summary counts none."""
    monkeypatch.setattr(licence_check, "run_pip_licenses", lambda _path: [])
    monkeypatch.setattr(licence_check, "find_data_licence_offenders", lambda: [])
    monkeypatch.setattr(licence_check, "find_own_licence_violations", lambda: [])
    monkeypatch.setattr("sys.argv", ["licence_check"])
    assert licence_check.main() == 0
    said = capsys.readouterr()
    assert "NOT YET PASSED" not in said.err
    assert "'git'" not in said.err
    assert "0 image runtime(s) not yet passed" in said.out
