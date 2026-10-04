"""Two tracked files must never differ only in case (`tools/case_collision_check.py`'s own docstring
has the reasoning). The planted pair is the red-then-green proof `CLAUDE.md` rule 15 asks for: the
check is shown to flag a violation of the exact shape it exists to catch before it is trusted on
the real tree, which it cannot create such a pair in (a case-insensitive disk refuses the second
file), which is why the proof is against the pure function and not a temporary directory."""

from __future__ import annotations

from tools.case_collision_check import case_collisions, tracked_paths


def test_a_pair_that_differs_only_in_case_is_flagged() -> None:
    paths = [
        "apps/workspace/src/inspector/LinkHistory.tsx",
        "apps/workspace/src/inspector/linkHistory.ts",
        "apps/workspace/src/inspector/LinkNotes.tsx",
    ]
    assert case_collisions(paths) == [
        (
            "apps/workspace/src/inspector/LinkHistory.tsx",
            "apps/workspace/src/inspector/linkHistory.ts",
        )
    ]


def test_a_folder_and_a_file_that_differ_only_in_case_are_flagged_too() -> None:
    paths = ["packages/Ontology/loader.py", "packages/ontology/loader.py"]
    assert case_collisions(paths) == [
        ("packages/Ontology/loader.py", "packages/ontology/loader.py")
    ]


def test_distinct_names_are_not_flagged() -> None:
    assert case_collisions(["a/B.ts", "a/b_c.ts", "A_b.ts"]) == []


def test_a_stylesheet_beside_its_component_is_not_a_module_collision() -> None:
    # A bare import never resolves to `.css`, so `Button.tsx` and `button.css` can share a folder.
    assert case_collisions(["src/design/Button.tsx", "src/design/button.css"]) == []


def test_a_test_file_is_not_its_subjects_collision() -> None:
    assert case_collisions(["src/x/Panel.tsx", "src/x/Panel.test.tsx", "src/x/panel.test.ts"]) == [
        ("src/x/Panel.test.tsx", "src/x/panel.test.ts")
    ]


def test_the_tracked_tree_has_no_such_pair() -> None:
    paths = tracked_paths()
    assert len(paths) > 1000, "the tracked-file listing came back implausibly short"
    assert case_collisions(paths) == []
