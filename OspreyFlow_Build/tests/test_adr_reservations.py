"""`tools/adr_reservations_check.py` (ADR-142 decision 5): every heading above the baseline in
`spec/06_DECISIONS.md` has a reservation row in `spec/ADR_RESERVATIONS.md`.

Rule 15: each planted violation is the shape a lane actually writes — a heading appended to the real
decision log, checked against the real reservations file — not a hand-made miniature.
"""

from __future__ import annotations

import re

import pytest
from tools.adr_reservations_check import (
    DECISIONS_PATH,
    KNOWN_DUPLICATE_HEADINGS,
    RESERVATIONS_PATH,
    find_doubled_lines,
    find_duplicate_headings,
    find_ledger_edits,
    find_stale_known_duplicates,
    find_unreserved,
    parse_baseline,
)

DECISIONS = DECISIONS_PATH.read_text(encoding="utf-8")
RESERVATIONS = RESERVATIONS_PATH.read_text(encoding="utf-8")


def _appended(*headings: str) -> str:
    body = "".join(f"\n\n{h}\n\nStatus: accepted from a planted ruling.\n" for h in headings)
    return DECISIONS + body


def test_the_real_decision_log_has_no_unreserved_heading() -> None:
    assert find_unreserved(DECISIONS, RESERVATIONS) == []


def test_an_unreserved_adr_heading_is_reported() -> None:
    planted = _appended("## ADR-199 — A planted record — ACCEPTED (design)")
    assert find_unreserved(planted, RESERVATIONS) == [
        "ADR-199 has a heading but no reservation row"
    ]


def test_an_unreserved_amendment_to_an_old_adr_is_reported() -> None:
    last = parse_baseline(RESERVATIONS).last_amendment[110]
    planted = _appended(f"### ADR-110, Amendment {last + 40} (7 November 2026) — planted")
    assert find_unreserved(planted, RESERVATIONS) == [
        f"ADR-110 Amendment {last + 40} has a heading but no reservation row"
    ]


def test_an_amendment_to_an_adr_with_none_at_the_baseline_is_reported() -> None:
    baseline = parse_baseline(RESERVATIONS)
    never_amended = next(n for n in range(1, baseline.last_adr) if n not in baseline.last_amendment)
    planted = _appended(f"### ADR-{never_amended:03d}, Amendment 1 (7 November 2026) — planted")
    assert find_unreserved(planted, RESERVATIONS) == [
        f"ADR-{never_amended:03d} Amendment 1 has a heading but no reservation row"
    ]


def test_an_amendment_heading_in_another_form_is_reported() -> None:
    planted = _appended("### Amendment 2 (7 November 2026): a planted amendment without its ADR")
    [problem] = find_unreserved(planted, RESERVATIONS)
    assert "not in the form '### ADR-n, Amendment m'" in problem


def test_a_reserved_heading_passes() -> None:
    reservations = RESERVATIONS + (
        "\n| ADR-199 | A planted record | studio | 2026-11-07 | reserved |\n"
    )
    planted = _appended("## ADR-199 — A planted record — ACCEPTED (design)")
    assert find_unreserved(planted, reservations) == []


def test_a_number_reserved_twice_is_reported() -> None:
    row = "| ADR-199 | A planted record | {lane} | 2026-11-07 | reserved |\n"
    reservations = RESERVATIONS + "\n" + row.format(lane="studio") + row.format(lane="glass")
    assert find_unreserved(DECISIONS, reservations) == ["ADR-199 is reserved 2 times"]


# --- a heading written twice (slice BL1b: what a union merge or a repeated commit leaves) ---------


def _last_block(pattern: str) -> tuple[str, str]:
    """The last real block of the log whose heading matches `pattern`: its name and its text."""
    start = list(re.finditer(pattern, DECISIONS, re.MULTILINE))[-1].start()
    following = re.search(r"\n#{2,3} ", DECISIONS[start + 1 :])
    end = start + 1 + following.start() if following else len(DECISIONS)
    return DECISIONS[start : DECISIONS.find("\n", start)], DECISIONS[start:end]


def test_the_real_log_has_only_its_one_known_repeated_heading() -> None:
    assert KNOWN_DUPLICATE_HEADINGS == {"ADR-148 Amendment 10": 2}
    assert find_duplicate_headings(DECISIONS) == []
    assert find_stale_known_duplicates(DECISIONS) == []


def test_an_amendment_block_appended_twice_is_reported() -> None:
    heading, block = _last_block(r"^### ADR-\d{3}, Amendment \d+\b")
    name = re.match(r"### (ADR-\d{3}), Amendment (\d+)", heading)
    assert name is not None
    key = f"{name.group(1)} Amendment {name.group(2)}"
    assert f"{key} has 2 headings in 06_DECISIONS.md (a block written twice)" in find_unreserved(
        DECISIONS + "\n" + block, RESERVATIONS
    )


def test_an_adr_block_written_twice_is_reported() -> None:
    heading, block = _last_block(r"^## ADR-\d{3}\b")
    key = re.match(r"## (ADR-\d{3})", heading)
    assert key is not None
    assert f"{key.group(1)} has 2 headings in 06_DECISIONS.md (a block written twice)" in (
        find_duplicate_headings(DECISIONS + "\n" + block)
    )


def test_a_third_copy_of_the_known_repeat_is_reported() -> None:
    heading, block = _last_block(r"^### ADR-148, Amendment 10\b")
    assert find_duplicate_headings(DECISIONS + "\n" + block) == [
        "ADR-148 Amendment 10 has 3 headings in 06_DECISIONS.md (a block written twice)"
    ]


def test_a_known_repeat_that_has_been_repaired_is_reported_as_stale() -> None:
    one_copy = DECISIONS[: DECISIONS.rindex("### ADR-148, Amendment 10")]
    assert find_stale_known_duplicates(one_copy) == [
        "ADR-148 Amendment 10 is in KNOWN_DUPLICATE_HEADINGS but has 1 heading(s): remove the entry"
    ]


# --- a doubled line in the reservations file ----------------------------------------------------


def _rows(status: str) -> list[str]:
    return [
        ln for ln in RESERVATIONS.splitlines() if ln.startswith("| ADR-") and f"| {status} |" in ln
    ]


def test_the_real_reservations_file_has_no_doubled_line() -> None:
    assert find_doubled_lines(RESERVATIONS) == []


def test_a_row_copied_twice_is_reported_as_doubled_and_as_reserved_twice() -> None:
    row = _rows("written")[-1]
    problems = find_unreserved(DECISIONS, RESERVATIONS + row + "\n")
    assert any(p.startswith("a line appears 2 times") and row[:40] in p for p in problems)
    assert any("is reserved 2 times" in p for p in problems)


def test_a_doubled_prose_line_is_reported() -> None:
    prose = next(ln for ln in RESERVATIONS.splitlines() if ln.startswith("Nothing at or below"))
    [problem] = find_doubled_lines(RESERVATIONS + prose + "\n")
    assert problem.startswith("a line appears 2 times") and prose in problem


def test_a_row_left_twice_with_two_statuses_is_reported() -> None:
    """What union leaves when one side flips a held row to written and the other rewords it but
    keeps it reserved: the same number, once `written` and once `reserved`."""
    held = _rows("reserved")[-1]
    flipped = held.replace("| reserved |", "| written |")
    title = held.split(" | ")[1]
    reworded = held.replace(title, title + ", reworded")
    assert flipped.endswith("| written |") and reworded.endswith("| reserved |")
    reservations = RESERVATIONS.replace(held, flipped + "\n" + reworded)
    number = held.split(" | ")[0][2:]
    assert f"{number} is reserved 2 times" in find_unreserved(DECISIONS, reservations)


# --- an edit to an existing line, not an append (compared with the merge-base)
# ----------------------


def _edited_row(change) -> str:
    """The real file with its last `written` row changed by `change(cells)`."""
    row = _rows("written")[-1]
    cells = row.strip("| ").rstrip(" |").split(" | ")
    return RESERVATIONS.replace(row, "| " + " | ".join(change(cells)) + " |")


def test_the_real_file_compared_with_itself_has_no_edit() -> None:
    assert find_ledger_edits(RESERVATIONS, RESERVATIONS) == []


_PLANTED = "| ADR-199 | A planted record | studio | 2026-11-20 | reserved |"


def _end_of_table(extra: str) -> str:
    """The real file with `extra` as the last row of the Reservations table, above `## Baseline`."""
    return RESERVATIONS.replace("\n## Baseline", extra + "\n\n## Baseline", 1)


def test_the_real_file_has_its_baseline_heading_once() -> None:
    assert RESERVATIONS.count("\n## Baseline\n") == 1


def test_a_row_added_at_the_end_of_the_reservations_table_is_allowed() -> None:
    """Where slice GG6 put its row (`496d7b9`): above `## Baseline`, not at the end of the file."""
    assert find_ledger_edits(RESERVATIONS, _end_of_table("\n" + _PLANTED)) == []


def test_a_row_added_in_the_middle_of_the_reservations_table_is_allowed() -> None:
    first_row = _rows("written")[0]
    inserted = RESERVATIONS.replace(first_row, first_row + "\n" + _PLANTED, 1)
    assert inserted != RESERVATIONS
    assert find_ledger_edits(RESERVATIONS, inserted) == []


def test_a_row_added_below_the_baseline_heading_is_reported() -> None:
    [problem] = find_ledger_edits(RESERVATIONS, RESERVATIONS + _PLANTED + "\n")
    assert problem.startswith("a row was added below '## Baseline'")
    assert "ADR-199" in problem


def test_a_row_added_inside_the_baseline_section_is_reported() -> None:
    marker = "Last ADR at the baseline"
    inserted = RESERVATIONS.replace(marker, _PLANTED + "\n" + marker, 1)
    [problem] = find_ledger_edits(RESERVATIONS, inserted)
    assert problem.startswith("a row was added below '## Baseline'")


def test_a_row_that_duplicates_a_row_of_the_base_is_reported() -> None:
    """The same number again in the table (what a union merge leaves of a row edited two ways)."""
    row = _rows("written")[0]
    number = row.split("|")[1].strip()
    [problem] = find_ledger_edits(RESERVATIONS, _end_of_table("\n" + row.replace("written", "reserved")))
    assert "duplicates a row of the base" in problem and number in problem


def test_a_row_flipped_from_reserved_to_written_is_allowed() -> None:
    held = _rows("reserved")[-1]
    flipped = RESERVATIONS.replace(held, held.replace("reserved", "written"))
    assert find_ledger_edits(RESERVATIONS, flipped) == []


def test_a_row_flipped_back_from_written_to_reserved_is_reported() -> None:
    done = _rows("written")[-1]
    flipped_back = RESERVATIONS.replace(done, done.replace("written", "reserved"))
    [problem] = find_ledger_edits(RESERVATIONS, flipped_back)
    assert "was edited, not appended to" in problem


@pytest.mark.parametrize(
    ("cell", "replacement"),
    [(0, "ADR-998 Amendment 9"), (1, "A different title"), (2, "another-lane"), (3, "2026-01-01")],
    ids=["number", "title", "lane", "date"],
)
def test_a_changed_cell_of_an_existing_row_is_reported(cell: int, replacement: str) -> None:
    def change(cells: list[str]) -> list[str]:
        return [replacement if i == cell else c for i, c in enumerate(cells)]

    row = _rows("written")[-1]
    edited = _edited_row(change)
    assert edited != RESERVATIONS
    [problem] = find_ledger_edits(RESERVATIONS, edited)
    assert row[:40] in problem


def test_a_removed_row_is_reported() -> None:
    row = _rows("written")[-1]
    [problem] = find_ledger_edits(RESERVATIONS, RESERVATIONS.replace(row + "\n", ""))
    assert problem.startswith("a line was removed or edited") and row[:40] in problem


def test_an_edited_prose_line_is_reported() -> None:
    edited = RESERVATIONS.replace("This section is never edited", "This section is edited")
    problems = find_ledger_edits(RESERVATIONS, edited)
    [removed] = [p for p in problems if p.startswith("a line was removed or edited")]
    assert "never edited after step 0" in removed


def test_an_added_line_that_is_not_a_row_is_reported() -> None:
    [problem] = find_ledger_edits(RESERVATIONS, RESERVATIONS + "A note, not a reservation.\n")
    assert problem.startswith("a line that is not a reservation row was added")


# A row shaped like the Baseline table's (`| ADR-n | m |`) matches the start of a reservation row
# but is not one; `parse_baseline` reads the whole file and the last occurrence wins, so
# appending one would quietly move the baseline the file says is never edited.


def test_an_appended_baseline_shaped_row_is_reported_and_would_have_moved_the_baseline() -> None:
    last_adr = max(parse_baseline(RESERVATIONS).last_amendment)
    planted = RESERVATIONS + f"| ADR-{last_adr:03d} | 999 |\n"
    assert parse_baseline(planted).last_amendment[last_adr] == 999  # the harm the check prevents
    [problem] = find_ledger_edits(RESERVATIONS, planted)
    assert problem.startswith("a line that is not a reservation row was added")
    assert f"| ADR-{last_adr:03d} | 999 |" in problem


def test_an_appended_malformed_row_is_reported() -> None:
    [problem] = find_ledger_edits(RESERVATIONS, RESERVATIONS + "| ADR-199 | x |\n")
    assert problem.startswith("a line that is not a reservation row was added")


def test_an_appended_row_with_an_unknown_status_is_reported() -> None:
    row = "| ADR-199 | A planted record | studio | 2026-11-20 | pending |\n"
    [problem] = find_ledger_edits(RESERVATIONS, RESERVATIONS + row)
    assert problem.startswith("a line that is not a reservation row was added")
