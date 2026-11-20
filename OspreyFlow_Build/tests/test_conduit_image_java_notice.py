"""The Conduit image carries the Java runtime's NOTICE and source offer (slice PL2a; `spec/06_DECISIONS.md`
ADR-147 Amendment 6, which brings `spec/00_ARCHITECTURE.md` §7's "a release step" to the image).

`services/api/Dockerfile`'s `runtime-included` stage copies `services/api/JAVA_NOTICE` to `/opt/java/NOTICE`,
beside the `legal` tree the `jlink` runtime carries: the runtime's name, version and licence, the offer of its
corresponding source, and the native libraries the runtime bundles. The build that omits Java, and the final
stage, carry none of it.

**Which test would fail if the notice were dropped from the image (rule 12):**
`test_the_included_stage_copies_the_notice_to_opt_java_notice` (the `COPY` line deleted from the real
Dockerfile), and `test_the_real_dockerfile_and_notice_are_clean` (it reads the real Dockerfile). Dropped from the
file instead: `test_a_notice_missing_or_drifting_is_flagged` (every field, the tag, the `jlink` line and each
library of the specification's table, each shown red). The omitted build and the final stage are held by
`test_no_other_stage_copies_the_notice` (and, for Java in the final stage, by
`tests/test_conduit_image_java_licence.py`).

Every case plants its violation in the shape the code meets at its real call site (rule 15): the real
Dockerfile with one line removed or changed, the real notice with one line changed, the real specification with
one row added; never a hand-written approximation. Each plant first asserts that it changed the text, so a plant
that missed its target fails the case instead of passing it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from tools.layout import BUILD, CORE
from tools.licence_check import _instructions, label_pairs

MARKETING = BUILD / "marketing_site"
sys.path.insert(0, str(MARKETING))

import client_hashes  # noqa: E402

DOCKERFILE_PATH = CORE / "services" / "api" / "Dockerfile"
NOTICE_PATH = CORE / "services" / "api" / "JAVA_NOTICE"
SPEC_00 = BUILD / "spec" / "00_ARCHITECTURE.md"
NOTICE_DESTINATION = "/opt/java/NOTICE"
VERSION_LABEL = "org.ospreyflow.runtime.java.version"
LICENCE_LABEL = "org.ospreyflow.runtime.java.licence"

DOCKERFILE = DOCKERFILE_PATH.read_text(encoding="utf-8")
SPEC = SPEC_00.read_text(encoding="utf-8")
#: The one line `COPY` makes, as the real Dockerfile writes it (the build context is the product folder).
COPY_LINE = f"COPY services/api/JAVA_NOTICE {NOTICE_DESTINATION}"
SYNTHETIC_CLIENT = "Example Shire Constabulary"


def _read_notice() -> str:
    assert NOTICE_PATH.is_file(), f"{NOTICE_PATH.relative_to(CORE)} is missing"
    return NOTICE_PATH.read_text(encoding="utf-8")


def _stage(text: str, name: str) -> str:
    """The instructions of the stage `name`, up to the next `FROM` (as the neighbouring test reads it)."""
    return text.split(f"\nFROM python:3.12-slim AS {name}\n", 1)[1].split("\nFROM ", 1)[0]


def _final(text: str) -> str:
    return text.rsplit("\nFROM ", 1)[1]


def _words(text: str) -> str:
    """Whitespace collapsed, so a wrapped line reads as the one it was cut from."""
    return " ".join(text.split())


def _copies(stage: str) -> list[tuple[list[str], str]]:
    """Each `COPY` of the stage that does not take from another stage: its sources and its destination."""
    found = []
    for instruction in _instructions(stage):
        word, _, rest = instruction.partition(" ")
        if word.upper() != "COPY":
            continue
        tokens = [t for t in rest.split() if not t.startswith("--")]
        if any(t.startswith("--from=") for t in rest.split()):
            continue
        found.append((tokens[:-1], tokens[-1]))
    return found


def _copies_of_the_notice(stage: str) -> list[str]:
    """The destinations of the stage's `COPY`s whose source is the notice file."""
    return [
        destination
        for sources, destination in _copies(stage)
        if any((CORE / source).resolve() == NOTICE_PATH.resolve() for source in sources)
    ]


def _labels(dockerfile: str) -> dict[str, str]:
    return dict(label_pairs(dockerfile))


def _jlink(dockerfile: str) -> str:
    (line,) = [i for i in _instructions(dockerfile) if i.startswith("RUN jlink")]
    return _words(line.removeprefix("RUN "))


def _base_image(dockerfile: str) -> str:
    match = re.search(r"^FROM (eclipse-temurin:\S+?)@sha256:[0-9a-f]{64} AS java$", dockerfile, re.M)
    assert match, "the Java stage is not `FROM eclipse-temurin:<tag>@sha256:<digest> AS java`"
    return match.group(1)


def _fields(notice: str) -> dict[str, str]:
    """The notice's `Name: value` lines (one line each), as a person and the test both read them."""
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"^(Runtime|Version|Licence|Source tag|Base image): (.+)$", notice, re.M)
    }


def bundled_libraries(spec: str) -> list[tuple[str, str]]:
    """The specification's table of the runtime's bundled native libraries: (library, licence) as
    written, backticks left out. Read from the specification so a library added there is asked of the notice."""
    lines = spec.splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith("| Library (as bundled)"))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        library, licence = (_words(cell.replace("`", "")) for cell in line.strip("| \n").split(" | ", 1))
        rows.append((library, licence))
    assert rows, "the specification's table of bundled libraries was not found"
    return rows


def dockerfile_problems(dockerfile: str) -> list[str]:
    problems = []
    included = _copies_of_the_notice(_stage(dockerfile, "runtime-included"))
    if included != [NOTICE_DESTINATION]:
        problems.append(f"the runtime-included stage must copy the notice once, to {NOTICE_DESTINATION}: {included}")
    if _copies_of_the_notice(_stage(dockerfile, "runtime-omitted")):
        problems.append("the runtime-omitted stage copies the notice")
    if _copies_of_the_notice(_final(dockerfile)):
        problems.append("the final stage copies the notice")
    # The notice says the licence texts are in /opt/java/legal: true only while the whole runtime is copied.
    whole = [
        i for i in _instructions(_stage(dockerfile, "runtime-included")) if i == "COPY --from=java /opt/jre /opt/java"
    ]
    if len(whole) != 1:
        problems.append("the runtime-included stage does not copy the whole of /opt/jre, so /opt/java/legal may not travel")
    return problems


def notice_problems(
    notice: str,
    dockerfile: str,
    spec: str,
    holders: list[str],
    hashes: set[str] | None,
) -> list[str]:
    problems = []
    fields = _fields(notice)
    labels = _labels(dockerfile)
    version, licence = labels[VERSION_LABEL], labels[LICENCE_LABEL]

    runtime = fields.get("Runtime", "")
    if "Eclipse Temurin" not in runtime or "OpenJDK" not in runtime:
        problems.append(f"Runtime: {runtime!r} does not name Eclipse Temurin and the OpenJDK")
    if fields.get("Base image") != _base_image(dockerfile):
        problems.append(f"Base image: {fields.get('Base image')!r} is not {_base_image(dockerfile)!r}")
    if fields.get("Version") != version:
        problems.append(f"Version: {fields.get('Version')!r} is not the label's {version!r}")
    if fields.get("Licence") != licence:
        problems.append(f"Licence: {fields.get('Licence')!r} is not the label's {licence!r}")

    if fields.get("Source tag") != f"jdk-{version}":
        problems.append(f"Source tag: {fields.get('Source tag')!r} is not jdk-{version}")
    if _jlink(dockerfile) not in _words(notice):
        problems.append("the jlink line of the Dockerfile is not in the notice as it stands")
    if "/opt/java/legal" not in notice:
        problems.append("the notice does not say where the licence texts are (/opt/java/legal)")

    flat = _words(notice)
    for library, library_licence in bundled_libraries(spec):
        if library not in flat or library_licence not in flat:
            problems.append(f"library: {library} / {library_licence} is not in the notice")

    for holder in holders:
        if holder in flat:
            problems.append("client: the notice names a holder the product's NOTICE files credit")
    if hashes is not None and client_hashes.named(notice, hashes):
        problems.append("client: the notice names a name on the owner's hashed list")
    return problems


def _holders() -> list[str]:
    """How the product's own NOTICE names the client: the holder in the copyright line of each Laurium entry
    (`OspreyFlow_Core/NOTICE`, one of the four files that keep the name). Read, never written here."""
    holders = []
    for line in (CORE / "NOTICE").read_text(encoding="utf-8").splitlines():
        if re.search(r"laurium|arrow-pd-parser", line, re.I):
            if m := re.search(r"Copyright(?: \(c\))? \d{4} (.+?)\s*$", line):
                holders.append(m.group(1))
    assert holders, "OspreyFlow_Core/NOTICE no longer shows a holder in a Laurium line; read the rule again"
    return holders


def _plant(text: str, old: str, new: str) -> str:
    assert old in text, f"the plant's target is not in the text: {old[:60]!r}"
    planted = text.replace(old, new)
    assert planted != text
    return planted


def _real() -> list[str]:
    return notice_problems(_read_notice(), DOCKERFILE, SPEC, _holders(), client_hashes.known())


# --- the real files ------------------------------------------------------------------------------------


def test_the_real_dockerfile_and_notice_are_clean() -> None:
    assert dockerfile_problems(DOCKERFILE) == []
    assert _real() == []


def test_the_hashed_list_was_read_or_the_gap_is_said() -> None:
    if client_hashes.known() is None:
        pytest.skip(client_hashes.ABSENT)


# --- the image ------------------------------------------------------------------------------------------


def test_the_included_stage_copies_the_notice_to_opt_java_notice() -> None:
    assert COPY_LINE in DOCKERFILE, "the real Dockerfile's line is not the shape this test plants"
    assert _copies_of_the_notice(_stage(DOCKERFILE, "runtime-included")) == [NOTICE_DESTINATION]
    # Plant: the line deleted.
    without = _plant(DOCKERFILE, COPY_LINE + "\n", "")
    assert any("must copy the notice once" in p for p in dockerfile_problems(without))
    # Plant: copied twice.
    twice = _plant(DOCKERFILE, COPY_LINE + "\n", COPY_LINE + "\n" + COPY_LINE + "\n")
    assert any("must copy the notice once" in p for p in dockerfile_problems(twice))
    # Plant: to another place.
    elsewhere = _plant(DOCKERFILE, COPY_LINE, "COPY services/api/JAVA_NOTICE /opt/NOTICE")
    assert any("must copy the notice once" in p for p in dockerfile_problems(elsewhere))


def test_no_other_stage_copies_the_notice() -> None:
    omitted_last = 'LABEL org.ospreyflow.runtime.java.included="omitted"'
    in_omitted = _plant(DOCKERFILE, omitted_last, omitted_last + "\n" + COPY_LINE)
    assert dockerfile_problems(in_omitted) == ["the runtime-omitted stage copies the notice"]
    in_final = _plant(DOCKERFILE, "USER 10001:10001", COPY_LINE + "\nUSER 10001:10001")
    assert dockerfile_problems(in_final) == ["the final stage copies the notice"]


def test_the_legal_tree_travels_only_while_the_whole_runtime_is_copied() -> None:
    narrowed = _plant(DOCKERFILE, "COPY --from=java /opt/jre /opt/java", "COPY --from=java /opt/jre/bin /opt/java/bin")
    assert any("/opt/java/legal" in p for p in dockerfile_problems(narrowed))


# --- the notice -----------------------------------------------------------------------------------------


def test_a_notice_missing_or_drifting_is_flagged() -> None:
    notice, labels = _read_notice(), _labels(DOCKERFILE)
    version, licence = labels[VERSION_LABEL], labels[LICENCE_LABEL]

    def problems(n: str = notice, d: str = DOCKERFILE, s: str = SPEC) -> list[str]:
        return notice_problems(n, d, s, _holders(), client_hashes.known())

    # The Dockerfile's version label changes; the notice stays.
    relabelled = _plant(DOCKERFILE, f'{VERSION_LABEL}="{version}"', f'{VERSION_LABEL}="21.0.14+1"')
    assert any(p.startswith("Version:") for p in problems(d=relabelled))
    # The Dockerfile's licence label changes.
    relicenced = _plant(DOCKERFILE, f'{LICENCE_LABEL}="{licence}"', f'{LICENCE_LABEL}="GPL-2.0-only"')
    assert any(p.startswith("Licence:") for p in problems(d=relicenced))
    # The notice's licence changes (the exception dropped), and its version.
    assert any(p.startswith("Licence:") for p in problems(_plant(notice, f"Licence: {licence}", "Licence: GPL-2.0-only")))
    assert any(p.startswith("Version:") for p in problems(_plant(notice, f"Version: {version}", "Version: 21.0.1+12")))
    # The runtime's name.
    assert any(p.startswith("Runtime:") for p in problems(_plant(notice, "Eclipse Temurin", "A runtime")))
    # The offer: no tag; a tag for another version.
    no_tag = "\n".join(line for line in notice.splitlines() if not line.startswith("Source tag:"))
    assert no_tag != notice
    assert any(p.startswith("Source tag:") for p in problems(no_tag))
    assert any(p.startswith("Source tag:") for p in problems(_plant(notice, f"jdk-{version}", "jdk-21.0.1+12")))
    # The offer: a jlink line that differs from the notice's, either way round.
    assert any("jlink" in p for p in problems(_plant(notice, "--compress=zip-6", "--compress=zip-9")))
    narrowed = _plant(DOCKERFILE, "java.sql,", "")
    assert any("jlink" in p for p in problems(d=narrowed))
    # The legal tree is not named.
    assert any("/opt/java/legal" in p for p in problems(_plant(notice, "/opt/java/legal", "the image")))


def test_every_library_in_the_specification_s_table_is_named() -> None:
    rows = bundled_libraries(SPEC)
    assert len(rows) >= 10
    notice = _read_notice()
    for library, licence in rows:
        # Each, deleted from the notice, is flagged by its own name.
        planted = _plant(notice, library, "a library")
        assert any(f"library: {library} " in p for p in notice_problems(planted, DOCKERFILE, SPEC, _holders(), None))
    # A library added to the specification's table and not to the notice (the real specification, one row more).
    row_line = next(line for line in SPEC.splitlines() if line.startswith("| Eastman Kodak"))
    added = _plant(SPEC, row_line, row_line + "\n| zlib 1.3.1 | the zlib licence |")
    assert any("library: zlib 1.3.1" in p for p in notice_problems(notice, DOCKERFILE, added, _holders(), None))


def test_the_licence_of_each_library_is_the_tables_wording() -> None:
    notice = _read_notice()
    library, licence = bundled_libraries(SPEC)[1]
    planted = _plant(notice, licence, "a licence")
    assert any(f"library: {library} " in p for p in notice_problems(planted, DOCKERFILE, SPEC, _holders(), None))


def test_the_notice_names_no_client() -> None:
    notice = _read_notice()
    holders = _holders()
    # Plant: a holder as the product's NOTICE writes it, in a sentence of the notice.
    planted = notice + f"\nSupplied by {holders[0]}.\n"
    assert any(p.startswith("client:") for p in notice_problems(planted, DOCKERFILE, SPEC, holders, None))
    # Plant, by hash: a synthetic name on a list of the test's own, as the website checks plant theirs.
    synthetic = {client_hashes.digest(SYNTHETIC_CLIENT)}
    planted = notice + f"\nSupplied by {SYNTHETIC_CLIENT}.\n"
    assert any(p.startswith("client:") for p in notice_problems(planted, DOCKERFILE, SPEC, [], synthetic))
    assert notice_problems(notice, DOCKERFILE, SPEC, [], synthetic) == []
    # The owner's own list, where this machine has it.
    if (hashes := client_hashes.known()) is None:
        pytest.skip(client_hashes.ABSENT)
    assert client_hashes.named(notice, hashes) == set()


def test_the_notice_holds_no_url_and_no_address() -> None:
    """Brief: no URL not already in the repository, and no address for the offer's contact (the owner's to give)."""
    notice = _read_notice()
    assert not re.search(r"https?://|www\.|@[\w-]+\.", notice)
    # The check is not vacuous: each shape it refuses, planted in the real notice.
    for planted in ("See https://example.invalid/source", "Write to offers@example.invalid", "See www.example.invalid"):
        assert re.search(r"https?://|www\.|@[\w-]+\.", notice + "\n" + planted)
