"""The panel frame's specification table (slice PL8a; the owner's rulings of 24 November 2026).

`spec/02_GLASS_FRONTEND.md` holds, for each of the ten panel actions, its id, whether it is kept (this tab only, or
this browser), its normal state and its scripts-off state; and the side panel's minimum width is 300 pixels, not the
240 the spec carried before the owner's ruling ("the minimum side width is 300, correct spec/02"). The store in
`packages/glass-shared/src/layout/panelFrameStore.ts` declares what it keeps in `PANEL_ACTION_STORAGE`, and the
plain-TypeScript tree must not import React (ADR-152 invariant I1).

Which test fails if the invariant is broken (rule 12):

* the table names an id the registry lacks, misses one it has, or repeats one: `test_the_table_names_all_ten_ids`
  (and the planted cases `test_a_table_missing_an_id_is_refused`, `test_a_table_with_an_invented_id_is_refused`,
  `test_a_table_repeating_an_id_is_refused`);
* a row has an empty cell, a "kept" value that is neither of the two, or a scripts-off cell that does not say "open":
  `test_every_row_is_complete` and `test_a_row_with_an_empty_cell_is_refused`;
* a scripts-off cell names a size, order or fold "kept" in this browser (with no script nothing reads the browser's
  storage, so the state is the default one): `test_no_scripts_off_cell_names_a_kept_value` and the planted cases
  `test_a_scripts_off_cell_naming_a_kept_height_is_refused` and `test_a_scripts_off_cell_naming_a_kept_order_is_refused`;
* the store keeps something the table says is for the tab only, or the other way: `test_the_store_keeps_what_the_table_says`
  and `test_a_store_that_disagrees_with_the_table_is_refused`;
* the minimum width is anything but 300 in the spec or in `layoutSizes.ts`, or a 240 minimum is back in the sashes'
  paragraph: `test_the_minimum_side_width_is_300_in_the_spec_and_the_code` and the planted cases beside it;
* React reaches the store's folder: `test_a_react_import_in_the_stores_folder_fails_the_gate`, shown clean beside it
  (`test_the_stores_folder_passes_the_gate_clean`).

Each guard is shown red on text shaped as the real file is (rule 15): the planted spec is the real spec with one thing
changed; the planted React import is the line a component would write, put at the store's own path.

**This test walks:** `OspreyFlow_Build/spec/02_GLASS_FRONTEND.md`;
`OspreyFlow_Core/packages/glass-shared/src/keyboard/actionRegistry.ts` (the registry); `.../src/layout/layoutSizes.ts`
and `.../src/layout/panelFrameStore.ts` (read); and a scratch copy of `OspreyFlow_Core/packages/glass-shared/src/layout/`
under `tmp_path` for the gate (copied, never written in the real folder). It runs `OspreyFlow_Core/scripts/no_react_check.mjs`
over that scratch tree and nothing else.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from tests.glass_trees.test_no_react_check import make_tree, run_check, write

BUILD = Path(__file__).resolve().parents[2]
CORE = BUILD.parent / "OspreyFlow_Core"
SPEC = BUILD / "spec" / "02_GLASS_FRONTEND.md"
REGISTRY = CORE / "packages/glass-shared/src/keyboard/actionRegistry.ts"
LAYOUT = CORE / "packages/glass-shared/src/layout"
STORE = LAYOUT / "panelFrameStore.ts"
SIZES = LAYOUT / "layoutSizes.ts"

TABLE_HEADING = "**The ten panel actions"
KEPT_WORDS = {"tab only": "tab", "this browser": "browser"}


def spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def registry_ids() -> list[str]:
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index('export const PANEL_FRAME_ACTIONS = defineActionRegistry("PANEL_FRAME_ACTIONS", [')
    block = text[text.index("[", start) : text.index("] as const", start)]
    block = re.sub(r"//[^\n]*", "", block)
    return re.findall(r'"([a-z0-9-]+)"', block)


def table_rows(text: str) -> list[list[str]]:
    """The cells of each row of the table that follows the heading, header and rule rows left out."""
    at = text.find(TABLE_HEADING)
    assert at != -1, "spec/02 has no table headed '**The ten panel actions'"
    rows: list[list[str]] = []
    started = False
    for line in text[at:].splitlines()[1:]:
        if line.startswith("|"):
            started = True
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if cells[0].lower().startswith("action id") or set("".join(cells)) <= set("-: "):
                continue
            rows.append(cells)
        elif started:
            break
    return rows


def row_id(row: list[str]) -> str:
    return row[0].strip("` ")


def check_ids(text: str, expected: list[str]) -> list[str]:
    ids = [row_id(row) for row in table_rows(text)]
    faults = []
    if len(ids) != len(set(ids)):
        faults.append(f"an id is repeated: {sorted({i for i in ids if ids.count(i) > 1})}")
    if set(ids) - set(expected):
        faults.append(f"ids the registry lacks: {sorted(set(ids) - set(expected))}")
    if set(expected) - set(ids):
        faults.append(f"ids the table lacks: {sorted(set(expected) - set(ids))}")
    return faults


def check_rows_complete(text: str) -> list[str]:
    faults = []
    for row in table_rows(text):
        if len(row) != 4 or any(not cell for cell in row):
            faults.append(f"{row[0] if row else '?'}: a row with {len(row)} cells or an empty cell")
            continue
        if row[1].lower() not in KEPT_WORDS:
            faults.append(f"{row_id(row)}: kept is '{row[1]}', not one of {sorted(KEPT_WORDS)}")
        if "open" not in row[3].lower():
            faults.append(f"{row_id(row)}: the scripts-off state does not say 'open'")
    return faults


# Words that promise a state only a script could read back from the browser's storage.
KEPT_PROMISE = re.compile(r"\b(kept|keeps|keep|stored|saved|remembered|last used|chosen)\b", re.IGNORECASE)


def check_scripts_off_names_no_kept_value(text: str) -> list[str]:
    """With no script nothing reads localStorage: a scripts-off cell must give the default state, never a kept one."""
    faults = []
    for row in table_rows(text):
        if len(row) == 4 and (found := KEPT_PROMISE.search(row[3])):
            faults.append(f"{row_id(row)}: the scripts-off cell says '{found.group(0)}': {row[3]}")
    return faults


def kept_by_id(text: str) -> dict[str, str]:
    return {row_id(row): KEPT_WORDS.get(row[1].lower(), row[1]) for row in table_rows(text)}


def store_storage(source: str) -> dict[str, str]:
    at = source.index("export const PANEL_ACTION_STORAGE")
    block = source[at : source.index("}", at)]
    return dict(re.findall(r'"([a-z0-9-]+)":\s*"(tab|browser)"', block))


def sashes_paragraph(text: str) -> str:
    at = text.index("**Resizing panels (ADR-086)")
    return text[at : text.index("\n\n", at)]


def check_minimum(text: str, sizes_source: str) -> list[str]:
    faults = []
    paragraph = sashes_paragraph(text)
    if not re.search(r"at least 300 pixels wide", paragraph):
        faults.append("the sashes' paragraph does not say the column is at least 300 pixels wide")
    if "240" in paragraph:
        faults.append("a 240 remains in the sashes' paragraph")
    if "24 November 2026" not in paragraph:
        faults.append("the sashes' paragraph does not cite the ruling of 24 November 2026")
    match = re.search(r"export const MIN_SIDE_WIDTH = (\d+);", sizes_source)
    if match is None or match.group(1) != "300":
        faults.append(f"MIN_SIDE_WIDTH is {match.group(1) if match else 'missing'}, not 300")
    return faults


# ------------------------------------------------------------------------------------------------ the real files


def test_the_registry_has_ten_ids() -> None:
    ids = registry_ids()
    assert len(ids) == 10 and len(set(ids)) == 10, ids


def test_the_table_names_all_ten_ids() -> None:
    assert check_ids(spec_text(), registry_ids()) == []
    assert len(table_rows(spec_text())) == 10


def test_every_row_is_complete() -> None:
    assert check_rows_complete(spec_text()) == []


def test_no_scripts_off_cell_names_a_kept_value() -> None:
    assert check_scripts_off_names_no_kept_value(spec_text()) == []


def test_the_timeline_rows_say_130px_with_no_script() -> None:
    rows = {row_id(row): row[3] for row in table_rows(spec_text())}
    for action in ("hide-and-show-the-timeline-by-keyboard", "resize-the-timeline-by-keyboard"):
        assert "130px" in rows[action], rows[action]


def test_the_store_keeps_what_the_table_says() -> None:
    assert STORE.exists(), "panelFrameStore.ts is not written"
    assert store_storage(STORE.read_text(encoding="utf-8")) == kept_by_id(spec_text())


def test_the_minimum_side_width_is_300_in_the_spec_and_the_code() -> None:
    assert check_minimum(spec_text(), SIZES.read_text(encoding="utf-8")) == []


def test_no_240_minimum_remains_for_the_side_panel() -> None:
    text = spec_text()
    near = [m.group(0) for m in re.finditer(r"[^\n]{0,160}\b240\b[^\n]{0,160}", text)]
    side = [line for line in near if re.search(r"side panel|right-hand column|the column|MIN_SIDE_WIDTH", line)]
    assert side == [], side


# ------------------------------------------------------------------------------- planted faults (rule 15)


def test_a_table_missing_an_id_is_refused() -> None:
    ids = registry_ids()
    lines = [line for line in spec_text().splitlines() if not line.startswith(f"| `{ids[3]}`")]
    assert len(lines) == len(spec_text().splitlines()) - 1, "the plant removed nothing: the row is not written as '| `id` |'"
    assert check_ids("\n".join(lines), ids) == [f"ids the table lacks: {[ids[3]]}"]


def test_a_table_with_an_invented_id_is_refused() -> None:
    ids = registry_ids()
    planted = spec_text().replace(f"| `{ids[0]}`", "| `hide-and-show-the-moon-by-keyboard`", 1)
    faults = check_ids(planted, ids)
    assert any("ids the registry lacks" in fault for fault in faults) and any("ids the table lacks" in fault for fault in faults)


def test_a_table_repeating_an_id_is_refused() -> None:
    ids = registry_ids()
    planted = spec_text().replace(f"| `{ids[1]}`", f"| `{ids[0]}`", 1)
    assert any("repeated" in fault for fault in check_ids(planted, ids))


def test_a_row_with_an_empty_cell_is_refused() -> None:
    ids = registry_ids()
    lines = spec_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(f"| `{ids[2]}`"))
    cells = lines[index].strip().strip("|").split("|")
    cells[2] = " "
    lines[index] = "|" + "|".join(cells) + "|"
    assert any(ids[2] in fault for fault in check_rows_complete("\n".join(lines)))


def test_a_row_kept_in_a_way_the_spec_does_not_name_is_refused() -> None:
    ids = registry_ids()
    lines = spec_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(f"| `{ids[4]}`"))
    cells = lines[index].strip().strip("|").split("|")
    cells[1] = " on the server "
    lines[index] = "|" + "|".join(cells) + "|"
    assert any("on the server" in fault for fault in check_rows_complete("\n".join(lines)))


def plant_scripts_off(row_index: int, cell: str) -> str:
    ids = registry_ids()
    lines = spec_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(f"| `{ids[row_index]}`"))
    cells = lines[index].strip().strip("|").split("|")
    cells[3] = f" {cell} "
    lines[index] = "|" + "|".join(cells) + "|"
    return "\n".join(lines)


def test_a_scripts_off_cell_naming_a_kept_height_is_refused() -> None:
    # The wording the table carried before round 5, in the cell it was in.
    planted = plant_scripts_off(2, "Open, its plot shown at the height kept or 130px, with no control")
    faults = check_scripts_off_names_no_kept_value(planted)
    assert len(faults) == 1 and "hide-and-show-the-timeline-by-keyboard" in faults[0], faults


def test_a_scripts_off_cell_naming_a_kept_order_is_refused() -> None:
    planted = plant_scripts_off(3, "Open in the order stored in this browser, with no control")
    faults = check_scripts_off_names_no_kept_value(planted)
    assert len(faults) == 1 and "stored" in faults[0], faults


def test_a_store_that_disagrees_with_the_table_is_refused() -> None:
    source = STORE.read_text(encoding="utf-8")
    ids = registry_ids()
    flipped = source.replace(f'"{ids[0]}": "tab"', f'"{ids[0]}": "browser"', 1)
    assert flipped != source, "the plant changed nothing: the first action is not declared as 'tab'"
    assert store_storage(flipped) != kept_by_id(spec_text())


def test_a_240_minimum_is_refused() -> None:
    sizes = SIZES.read_text(encoding="utf-8")
    planted = spec_text().replace("at least 300 pixels wide", "at least 240 pixels wide", 1)
    assert planted != spec_text()
    faults = check_minimum(planted, sizes)
    assert any("300 pixels wide" in fault for fault in faults) and any("240" in fault for fault in faults)


def test_a_code_minimum_that_is_not_300_is_refused() -> None:
    sizes = SIZES.read_text(encoding="utf-8")
    planted = sizes.replace("export const MIN_SIDE_WIDTH = 300;", "export const MIN_SIDE_WIDTH = 240;")
    assert planted != sizes
    assert check_minimum(spec_text(), planted) == ["MIN_SIDE_WIDTH is 240, not 300"]


def test_a_ruling_not_cited_is_refused() -> None:
    sizes = SIZES.read_text(encoding="utf-8")
    planted = spec_text().replace("24 November 2026", "the day before", 1)
    assert any("ruling" in fault for fault in check_minimum(planted, sizes))


# ----------------------------------------------------------------------------------------- the React gate


def scratch_with_layout(root: Path) -> Path:
    make_tree(root)
    target = root / "packages/glass-shared/src/layout"
    shutil.copytree(LAYOUT, target, ignore=shutil.ignore_patterns("*.test.ts"))
    return target


def test_the_stores_folder_passes_the_gate_clean(tmp_path: Path) -> None:
    # The same folder, copied as it is; the zustand the store imports is `zustand/vanilla`, which the scratch
    # tree has no package for, so the copy is checked at the source level (imports named, none React).
    scratch_with_layout(tmp_path)
    code, output = run_check(tmp_path)
    assert code == 0, output
    assert "react" not in output.lower().replace("no react", "")


def test_a_react_import_in_the_stores_folder_fails_the_gate(tmp_path: Path) -> None:
    target = scratch_with_layout(tmp_path)
    store = target / "panelFrameStore.ts"
    assert store.exists(), "panelFrameStore.ts is not written"
    # The line a component would write, put first in the store's own file.
    write(store, 'import { useSyncExternalStore } from "react";\n' + store.read_text(encoding="utf-8"))
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "FAIL" in output and "panelFrameStore.ts" in output and "react" in output


@pytest.mark.parametrize("name", ["panelFrameStore.ts", "panelFrameAttach.ts"])
def test_each_file_of_the_frame_exists(name: str) -> None:
    assert (LAYOUT / name).exists(), f"{name} is not written"
