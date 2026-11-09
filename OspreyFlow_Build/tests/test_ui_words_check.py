"""`tools/ui_words_check.py` — no "target model" in the Glass's user-facing copy (ADR-140 Amendment 9
decision 1: the screens say *domain model*; the code and spec 01 keep `TargetModel`). Shown red against
plants in the shapes the Glass's own strings take (CLAUDE.md rule 15): JSX text, an `aria-label`, a
template literal, a quoted constant in a words table, JSX text broken across lines, and a JSON copy
file. Shown not to fire on what is not copy: comments, identifiers and right ids."""

from __future__ import annotations

from pathlib import Path

from tools import ui_words_check
from tools.ui_words_check import find_banned, strip_comments


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


# Each plant is the shape a real Glass string had before L1.8 (ModelTab.tsx's heading and section
# label, NodePreview.tsx's words table, NodeDrawer.tsx's StagePanel words).
PLANTS = {
    "ingest/studio/ModelTab.tsx": (
        '    <section aria-label="Target model" style={{ padding: "var(--sp-16)" }}>\n'
        '      <h2 style={{ margin: 0 }}>Target model for {datasetName}</h2>\n'
    ),
    "ingest/dag/NodePreview.tsx": (
        "const WORDS = {\n"
        '  ontology_violation: "The map does not match the target model. Open the map editor.",\n'
        "};\n"
    ),
    "ingest/dag/NodeDrawer.tsx": (
        '        <StagePanel title="Map" words="Bind the columns to the target model." />\n'
    ),
    "ingest/x/Template.tsx": "const title = `The target   model for ${name}`;\n",
    "ingest/x/Wrapped.tsx": "      <p>\n        Change the target\n        model here.\n      </p>\n",
    "ingest/x/single.ts": "const s = 'the TARGET MODEL';\n",
    "shell/copy.json": '{ "about": "Edit the target model of a dataset." }\n',
}


def test_each_planted_shape_is_found(tmp_path: Path) -> None:
    found = find_banned(_tree(tmp_path, PLANTS))
    assert sorted({path for path, _, _ in found}) == sorted(PLANTS)
    # ModelTab's two plants are two findings, each on its own line.
    assert [line for path, line, _ in found if path == "ingest/studio/ModelTab.tsx"] == [1, 2]
    # The wrapped JSX text is reported at the line the phrase starts on.
    assert [line for path, line, _ in found if path == "ingest/x/Wrapped.tsx"] == [2]


def test_what_is_not_copy_is_not_found(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "a/types.ts": "import type { TargetModel } from './generated';\nconst m: TargetModel = x;\n",
            "a/rights.ts": 'const RIGHT = "edit_target_model";\nconst k = { edit_target_model: 1 };\n',
            "a/comments.tsx": (
                "// The target model in words, from the packs (ADR-126).\n"
                "/* the target\n   model, as spec 01 calls it */\n"
                '<p>{/* target model */}Domain model</p>\n'
                'const url = "https://example.invalid/a"; // target model\n'
            ),
            "a/Words.test.tsx": '<h2>Target model</h2>\n',  # tests are not on screen
            "a/flow.spec.ts": '"Target model"\n',
            "generated/T.ts": "// target model\nexport interface TargetModel {}\n",
        },
    )
    assert find_banned(root) == []


def test_a_comment_marker_inside_a_string_does_not_hide_the_rest_of_the_line(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"a/x.tsx": 'const u = "http://a.invalid"; const w = "the target model";\n'})
    assert [line for _, line, _ in find_banned(root)] == [1]


def test_an_apostrophe_in_jsx_text_does_not_swallow_the_next_line(tmp_path: Path) -> None:
    # `don't` opens no string that runs on: a quoted string never spans a line in TS or JSX attributes.
    root = _tree(tmp_path, {"a/x.tsx": "<p>You don't have it.</p>\n<p>Open the target model.</p>\n"})
    assert [line for _, line, _ in find_banned(root)] == [2]


def test_strip_comments_keeps_line_numbers() -> None:
    text = "a /* b\nc */ d\n// e\nf"
    assert strip_comments(text).count("\n") == text.count("\n")


def test_main_fails_on_a_plant_and_passes_without(tmp_path: Path, monkeypatch) -> None:
    root = _tree(tmp_path, {"ok.tsx": "<h2>Domain model for {name}</h2>\n"})
    monkeypatch.setattr(ui_words_check, "GLASS_SRC", root)
    assert ui_words_check.main() == 0
    (root / "bad.tsx").write_text("<h2>Target model for {name}</h2>\n", encoding="utf-8")
    assert ui_words_check.main() == 1


def test_the_real_glass_has_none() -> None:
    assert find_banned(ui_words_check.GLASS_SRC) == []
