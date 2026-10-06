"""`tools/colour_drift_check.py` — every colour literal in the Glass is one DESIGN.md holds (ADR-097,
taking the place of the design review's `npx impeccable detect`). Shown red against planted
literals in the shapes the real code uses (CLAUDE.md rule 15): a hex in a style object, an `rgba`
in a canvas fill, a CSS fallback inside `var(...)`."""

from __future__ import annotations

from pathlib import Path

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
