"""`tools/colour_drift_check.py` — every colour literal in the Glass is one DESIGN.md holds (ADR-097,
taking the place of the design review's `npx impeccable detect`). Shown red against planted
literals in the shapes the real code uses (CLAUDE.md rule 15): a hex in a style object, an `rgba`
in a canvas fill, a CSS fallback inside `var(...)`."""

from __future__ import annotations

from pathlib import Path

from tools import colour_drift_check
from tools.colour_drift_check import find_drift, palette_from


DESIGN = "| `--brass` | `#c08a34` | `#8a6318` |\n| x | `#161a1b` | `#f1f4f5` |\n"


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_colour_off_the_palette_is_found_in_each_shape_the_code_uses(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "a/MapCanvas.tsx": 'const LINK_FROM_COLOR = "#5b9bd5";\n',
            "b/Canvas.tsx": '  fill="rgba(192,138,52,0.15)"\n',
            "c/style.css": ".x { background: var(--n11, #1c1f20); }\n",
            "d/ok.tsx": 'const BRASS = "#C08A34"; // on the palette, any case\n',
        },
    )
    drift = find_drift(root, palette_from(DESIGN), mirrors=frozenset(), allowed=set())
    assert [(path, literal) for path, _, literal in drift] == [
        ("a/MapCanvas.tsx", "#5b9bd5"),
        ("b/Canvas.tsx", "rgba(192,138,52,0.15)"),
        ("c/style.css", "#1c1f20"),
    ]


def test_a_declared_mirror_and_an_allowlisted_literal_pass(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"color/tokens.ts": '"#deadbe"\n', "m/Map.tsx": '"#5b9bd5"\n'})
    drift = find_drift(
        root,
        palette_from(DESIGN),
        mirrors=frozenset({"color/tokens.ts"}),
        allowed={("m/Map.tsx", "#5b9bd5")},
    )
    assert drift == []


def test_tests_and_the_tokens_file_are_not_scanned(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"x.test.ts": '"#123456"\n', "design/tokens.css": "--a:#123456;\n"})
    assert find_drift(root, palette_from(DESIGN), mirrors=frozenset(), allowed=set()) == []


def test_the_real_glass_has_no_new_drift() -> None:
    from tools.colour_drift_check import main

    assert main() == 0


# --- a stale allowlist entry (found 6 October 2026: `#10131a` was fixed in `oklab.ts` and its line
# stayed, so the gate would have let the literal back in without a word) ---------------------------


def test_an_allowlist_entry_whose_literal_is_gone_is_reported(tmp_path: Path) -> None:
    (tmp_path / "color").mkdir()
    (tmp_path / "color" / "oklab.ts").write_text('const DARK = "#101314";\n', encoding="utf-8")
    palette = frozenset({"#101314"})
    allowed = {("color/oklab.ts", "#10131a"), ("missing/file.ts", "#123456")}
    assert colour_drift_check.stale_allowlist(tmp_path, palette, allowed) == [
        ("color/oklab.ts", "#10131a"),
        ("missing/file.ts", "#123456"),
    ]


def test_an_allowlist_entry_still_in_use_is_not_stale(tmp_path: Path) -> None:
    (tmp_path / "map").mkdir()
    (tmp_path / "map" / "MapView.tsx").write_text('paint: "rgba(0,0,0,0.4)"\n', encoding="utf-8")
    assert colour_drift_check.stale_allowlist(tmp_path, frozenset(), {("map/MapView.tsx", "rgba(0,0,0,0.4)")}) == []


def test_an_allowlisted_literal_that_is_now_on_the_palette_is_stale(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text('"#101314"\n', encoding="utf-8")
    assert colour_drift_check.stale_allowlist(tmp_path, frozenset({"#101314"}), {("a.ts", "#101314")}) == [
        ("a.ts", "#101314")
    ]
