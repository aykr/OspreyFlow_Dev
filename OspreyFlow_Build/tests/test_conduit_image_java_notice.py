"""The Conduit image carries the Java runtime's NOTICE and source offer (slice PL2a; `spec/06_DECISIONS.md`
ADR-147 Amendment 6, which brings `spec/00_ARCHITECTURE.md` §7's "a release step" to the image).

`services/api/Dockerfile`'s `runtime-included` stage copies `notices/JAVA_NOTICE` to `/opt/java/NOTICE`,
beside the `legal` tree the `jlink` runtime carries: the runtime's name, version and licence, the offer of its
corresponding source, and the native libraries the runtime bundles. The build that omits Java, and the final
stage, carry none of it, by any route: the file lives in `notices/`, a folder the builder stage does not copy,
because a file under `services/` would be copied whole by the builder's `COPY services ./services` and again by
the final stage's `COPY --from=builder /app/services ./services`, into the image that has no Java (round 2's fault).

**Which test would fail if the notice were dropped from the image (rule 12):**
`test_the_included_stage_copies_the_notice_to_opt_java_notice` (the `COPY` line deleted from the real
Dockerfile), and `test_the_real_dockerfile_and_notice_are_clean` (it reads the real Dockerfile). Dropped from the
file instead: `test_a_notice_missing_or_drifting_is_flagged` (every field, the tag, the `jlink` line and each
library of the specification's table, each shown red). The omitted build and the final stage are held by
`test_no_other_stage_copies_the_notice` (a `COPY` of the file itself) and
`test_no_route_carries_the_notice_into_the_omitted_image` (a folder copy that contains it, and the final stage's
`COPY --from=builder` that brings it in: the real Dockerfile with the notice put back under `services/`, and with
a `notices` folder copied through) and `test_an_add_or_a_builder_copy_into_the_omitted_image_is_flagged` (an `ADD`
of the file or the folder in either stage, and the omitted stage's own `COPY --from=builder`); for Java in the
final stage, `tests/test_conduit_image_java_licence.py`.
Each library is tied to its own licence by `test_the_licence_of_each_library_is_the_tables_wording`, one row at a
time.

Every case plants its violation in the shape the code meets at its real call site (rule 15): the real
Dockerfile with one line removed or changed, the real notice with one line changed, the real specification with
one row added; never a hand-written approximation. Each plant first asserts that it changed the text, so a plant
that missed its target fails the case instead of passing it.
"""

from __future__ import annotations

import posixpath
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
NOTICE_PATH = CORE / "notices" / "JAVA_NOTICE"
SPEC_00 = BUILD / "spec" / "00_ARCHITECTURE.md"
NOTICE_DESTINATION = "/opt/java/NOTICE"
VERSION_LABEL = "org.ospreyflow.runtime.java.version"
LICENCE_LABEL = "org.ospreyflow.runtime.java.licence"

DOCKERFILE = DOCKERFILE_PATH.read_text(encoding="utf-8")
SPEC = SPEC_00.read_text(encoding="utf-8")
#: The one line `COPY` makes, as the real Dockerfile writes it (the build context is the product folder).
COPY_LINE = f"COPY notices/JAVA_NOTICE {NOTICE_DESTINATION}"
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


def _copies(stage: str) -> list[tuple[list[str], str, str | None]]:
    """Each `COPY` or `ADD` of the stage (`ADD` puts a file or folder of the context into the image just as `COPY`
    does): its sources, its destination, and the stage it takes from (None: the context)."""
    found = []
    for instruction in _instructions(stage):
        word, _, rest = instruction.partition(" ")
        if word.upper() not in ("COPY", "ADD"):
            continue
        tokens = rest.split()
        origin = next((t.removeprefix("--from=") for t in tokens if t.startswith("--from=")), None)
        tokens = [t for t in tokens if not t.startswith("--")]
        found.append((tokens[:-1], tokens[-1], origin))
    return found


def _holds(source: str, notice_path: Path) -> bool:
    """Whether a build-context source (a file, a folder or a pattern) is the notice or contains it."""
    wild = any(c in source for c in "*?[")
    candidates = list(CORE.glob(source)) if wild else [CORE / source]
    n = notice_path.resolve()
    return any(c.resolve() == n or c.resolve() in n.parents for c in candidates)


def _copies_of_the_notice(stage: str, notice_path: Path = NOTICE_PATH) -> list[str]:
    """The destinations of the stage's context `COPY`s whose source is the notice file or a folder holding it."""
    return [
        destination
        for sources, destination, origin in _copies(stage)
        if origin is None and any(_holds(source, notice_path) for source in sources)
    ]


def _landings_in_the_builder(dockerfile: str, notice_path: Path) -> list[str]:
    """Where in the builder stage's image the notice lands (its `WORKDIR` is /app, read from the stage)."""
    builder = _stage(dockerfile, "builder")
    workdir = next(i.split(None, 1)[1] for i in _instructions(builder) if i.startswith("WORKDIR "))
    landings = []
    for sources, destination, origin in _copies(builder):
        for source in sources:
            if origin is None and _holds(source, notice_path):
                into = posixpath.normpath(posixpath.join(workdir, destination))
                held = (CORE / source).resolve()
                rest = "" if held == notice_path.resolve() else notice_path.resolve().relative_to(held).as_posix()
                landings.append(posixpath.join(into, rest) if rest else into)
    return landings


def _brought_from_the_builder(stage: str, landings: list[str]) -> list[str]:
    """The landings of the notice that the stage's `COPY --from=builder` carry on into it."""
    carried = []
    for sources, _destination, origin in _copies(stage):
        if origin != "builder":
            continue
        for source in sources:
            root = posixpath.normpath(source)
            carried += [land for land in landings if land == root or land.startswith(root.rstrip("/") + "/")]
    return carried


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


def dockerfile_problems(dockerfile: str, notice_path: Path = NOTICE_PATH) -> list[str]:
    problems = []
    included = _copies_of_the_notice(_stage(dockerfile, "runtime-included"), notice_path)
    if included != [NOTICE_DESTINATION]:
        problems.append(f"the runtime-included stage must copy the notice once, to {NOTICE_DESTINATION}: {included}")
    omitted = _stage(dockerfile, "runtime-omitted")
    if _copies_of_the_notice(omitted, notice_path):
        problems.append("the runtime-omitted stage copies the notice")
    final = _final(dockerfile)
    if _copies_of_the_notice(final, notice_path):
        problems.append("the final stage copies the notice")
    # Both the omitted stage and the final stage (which serves both builds) reach the image with no Java, so
    # what either takes from the builder must not hold the notice.
    landings = _landings_in_the_builder(dockerfile, notice_path)
    if brought := _brought_from_the_builder(omitted, landings):
        problems.append(f"the runtime-omitted stage brings the notice in from the builder: {brought}")
    if brought := _brought_from_the_builder(final, landings):
        problems.append(f"the final stage brings the notice in from the builder, into the image without Java: {brought}")
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
    lines = [_words(line) for line in notice.splitlines()]
    for library, library_licence in bundled_libraries(spec):
        # Each library with its own licence, as one `Library: licence` line: a licence found elsewhere in the
        # notice (four rows share MIT) does not stand for this library's.
        if f"{library}: {library_licence}" not in lines:
            problems.append(f"library: {library} / {library_licence} is not in the notice, on one line")

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
    elsewhere = _plant(DOCKERFILE, COPY_LINE, "COPY notices/JAVA_NOTICE /opt/NOTICE")
    assert any("must copy the notice once" in p for p in dockerfile_problems(elsewhere))


def test_no_other_stage_copies_the_notice() -> None:
    omitted_last = 'LABEL org.ospreyflow.runtime.java.included="omitted"'
    in_omitted = _plant(DOCKERFILE, omitted_last, omitted_last + "\n" + COPY_LINE)
    assert dockerfile_problems(in_omitted) == ["the runtime-omitted stage copies the notice"]
    in_final = _plant(DOCKERFILE, "USER 10001:10001", COPY_LINE + "\nUSER 10001:10001")
    assert dockerfile_problems(in_final) == ["the final stage copies the notice"]


OLD_PLACE = CORE / "services" / "api" / "JAVA_NOTICE"


def test_no_route_carries_the_notice_into_the_omitted_image() -> None:
    """The final stage serves both builds. A folder copy that holds the notice, taken on by the final stage's
    `COPY --from=builder`, puts it into the image that has no Java, though no line names the file."""
    builder_copy = "\nCOPY services ./services\n"
    final_copy = "\nCOPY --from=builder /app/services ./services\n"
    assert DOCKERFILE.count(builder_copy) == 1 and DOCKERFILE.count(final_copy) == 1, "the real Dockerfile's lines are not the shape planted"
    # The real Dockerfile as it stands: the notice is outside every folder the builder copies.
    assert _landings_in_the_builder(DOCKERFILE, NOTICE_PATH) == []
    # Plant 1 (round 2's fault, exactly): the notice back under services/, the real Dockerfile's included-stage line
    # pointing at it; the builder's `COPY services ./services` and the final stage's copy of it now carry it.
    back = _plant(DOCKERFILE, COPY_LINE, "COPY services/api/JAVA_NOTICE /opt/java/NOTICE")
    assert _landings_in_the_builder(back, OLD_PLACE) == ["/app/services/api/JAVA_NOTICE"]
    problems = dockerfile_problems(back, OLD_PLACE)
    assert len(problems) == 1 and "brings the notice in from the builder" in problems[0], problems
    # Plant 2: the notice's own folder copied by the builder and taken on by the final stage.
    through = _plant(DOCKERFILE, builder_copy, builder_copy + "COPY notices ./notices\n")
    through = _plant(through, final_copy, final_copy + "COPY --from=builder /app/notices ./notices\n")
    problems = dockerfile_problems(through)
    assert len(problems) == 1 and "brings the notice in from the builder" in problems[0], problems
    # Plant 3: the whole of /app taken on, which holds the folder the builder copied.
    whole = _plant(through, "COPY --from=builder /app/notices ./notices", "COPY --from=builder /app ./")
    assert any("brings the notice in" in p for p in dockerfile_problems(whole))
    # Plant 4: a folder copy that holds the notice, straight from the context, in each of the other stages.
    omitted_last = 'LABEL org.ospreyflow.runtime.java.included="omitted"'
    assert dockerfile_problems(_plant(DOCKERFILE, omitted_last, omitted_last + "\nCOPY notices /x")) == [
        "the runtime-omitted stage copies the notice"
    ]
    assert dockerfile_problems(_plant(DOCKERFILE, "USER 10001:10001", "COPY notices /x\nUSER 10001:10001")) == [
        "the final stage copies the notice"
    ]
    # Not over-flagged: a builder that copies the folder, with the final stage taking nothing of it, ships nothing.
    only_builder = _plant(DOCKERFILE, builder_copy, builder_copy + "COPY notices ./notices\n")
    assert dockerfile_problems(only_builder) == []


def test_an_add_or_a_builder_copy_into_the_omitted_image_is_flagged() -> None:
    """`ADD` puts the notice into a stage as surely as `COPY`, and the omitted stage can take it from the builder
    as the final stage can: the header's "by any route", each route planted in the real Dockerfile."""
    omitted_last = 'LABEL org.ospreyflow.runtime.java.included="omitted"'
    builder_copy = "\nCOPY services ./services\n"
    omitted_flag = ["the runtime-omitted stage copies the notice"]
    final_flag = ["the final stage copies the notice"]
    add_file = f"ADD notices/JAVA_NOTICE {NOTICE_DESTINATION}"
    # No `ADD` in the real Dockerfile, so the parse has nothing to be fooled by today.
    assert not [i for i in _instructions(DOCKERFILE) if i.split(" ", 1)[0].upper() == "ADD"]
    # `ADD` of the file itself, and of a folder holding it (with a flag, as `ADD --chmod=...` is written), in each stage.
    assert dockerfile_problems(_plant(DOCKERFILE, omitted_last, omitted_last + "\n" + add_file)) == omitted_flag
    assert dockerfile_problems(_plant(DOCKERFILE, omitted_last, omitted_last + "\nADD notices /x")) == omitted_flag
    assert dockerfile_problems(_plant(DOCKERFILE, omitted_last, omitted_last + "\nADD --chmod=0444 notices /x")) == omitted_flag
    assert dockerfile_problems(_plant(DOCKERFILE, "USER 10001:10001", add_file + "\nUSER 10001:10001")) == final_flag
    assert dockerfile_problems(_plant(DOCKERFILE, "USER 10001:10001", "add notices /x\nUSER 10001:10001")) == final_flag
    # In the included stage, `ADD` is read as a copy: in place of the `COPY` it is clean, and added twice it is flagged.
    assert dockerfile_problems(_plant(DOCKERFILE, COPY_LINE, add_file)) == []
    twice = _plant(DOCKERFILE, COPY_LINE, COPY_LINE + "\n" + add_file)
    assert any("must copy the notice once" in p for p in dockerfile_problems(twice))
    # The omitted stage taking the notice's folder from the builder, which copied it (the final stage's route, in the
    # other stage); and the whole of /app.
    builder_has = _plant(DOCKERFILE, builder_copy, builder_copy + "COPY notices ./notices\n")
    carried = _plant(builder_has, omitted_last, omitted_last + "\nCOPY --from=builder /app/notices /x")
    problems = dockerfile_problems(carried)
    assert len(problems) == 1 and "runtime-omitted stage brings the notice in from the builder" in problems[0], problems
    everything = _plant(builder_has, omitted_last, omitted_last + "\nCOPY --from=builder /app /x")
    assert any("runtime-omitted stage brings the notice in" in p for p in dockerfile_problems(everything))
    # Not over-flagged: the omitted stage taking something else from the builder, or the builder alone holding it.
    other = _plant(builder_has, omitted_last, omitted_last + "\nCOPY --from=builder /app/packages /x")
    assert dockerfile_problems(other) == []


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
    """Each row, one at a time: only that row's line changes, so a licence that other rows share (four are MIT)
    cannot stand in for it."""
    notice = _read_notice()
    for library, licence in bundled_libraries(SPEC):
        line = f"{library}: {licence}"
        assert line in notice.splitlines(), f"the notice has no line {line!r}"
        planted = _plant(notice, line, f"{library}: a licence")
        problems = notice_problems(planted, DOCKERFILE, SPEC, _holders(), None)
        assert [p for p in problems if p.startswith("library:")] == [
            f"library: {library} / {licence} is not in the notice, on one line"
        ], (library, problems)
    # The case the finding named, in the real notice: GIFLIB given another licence, the other MIT lines untouched.
    giflib = _plant(notice, "GIFLIB 6.1.3: MIT", "GIFLIB 6.1.3: BSD-3-Clause")
    assert notice.count("MIT") > 1 and "MIT" in giflib
    assert any("library: GIFLIB 6.1.3" in p for p in notice_problems(giflib, DOCKERFILE, SPEC, _holders(), None))
    # A licence moved to another library's line (swapped): each line still holds the other's text somewhere.
    swapped = _plant(notice, "GIFLIB 6.1.3: MIT", "GIFLIB 6.1.3: the IJG licence")
    assert any("library: GIFLIB 6.1.3" in p for p in notice_problems(swapped, DOCKERFILE, SPEC, _holders(), None))


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
