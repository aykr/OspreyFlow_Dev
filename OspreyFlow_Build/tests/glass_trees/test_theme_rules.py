"""The theme-rule check (`tools/theme_rule_check.py`; build id PL12, slice PL12b; ADR-152 Am. 4).

A theme's CSS rule outside its own folder (`OspreyFlow_Core/packages/themes/<name>/`) is found.
Today's GOV.UK rules outside any theme folder are the allowlist
(`tests/fixtures/theme_rule_allowlist.txt`), and the allowlist may only shrink: an entry added, an
entry whose rule is gone, and a recorded count that is not the number of entries each fail. Nothing
is moved by this slice; the check is not in `make ci` until the owner applies the Makefile diff, so
this file is where it is shown red (rule 15).

**Which folders this file walks (the scan row is written from this).** Only to build a *copy* of the
style-bearing files the check reads, in a temporary folder: under `OspreyFlow_Core`,
`packages/design`, `packages/glass-shared/src`, `apps/workspace/src`, `apps/workspace/scripts`,
`apps/pages` and `apps/harness/src` (the stylesheets, the templates, `fonts*.json`; `node_modules`
and `dist` pruned by name), and the two sign-in theme files in `harness/` by name. Every plant is
written into that copy under `tmp_path`; no real file is written. The real-tree cases run the check
itself over `OspreyFlow_Core`, which reads the same folders (and `packages/themes`, absent today).

Every plant takes the shape the check really meets: the real brand rules are `[data-brand="govuk"]`
blocks and `.…--govuk` modifier classes in stylesheets, and `[data-brand="govuk"]` rules inside a
Python triple-quoted string (`harness/keycloak_theme.py`)."""

from __future__ import annotations

import os
import shutil
from collections import Counter
from pathlib import Path

import pytest
from tools import theme_rule_check as trc
from tools.layout import BUILD, CORE

ALLOWLIST = BUILD / "tests" / "fixtures" / "theme_rule_allowlist.txt"

#: The folders under `OspreyFlow_Core` this file copies from, named here and not read from the
#: tool, so a tool that drops a root cannot also drop it from the copy the plants go into.
WALKED = (
    "packages/design",
    "packages/glass-shared/src",
    "apps/workspace/src",
    "apps/workspace/scripts",
    "apps/pages",
    "apps/harness/src",
)
SIGN_IN_FILES = ("harness/keycloak_theme.py", "harness/govuk_chrome.js")
PRUNED = {"node_modules", "dist", ".git", "__pycache__"}


def _style_bearing(path: Path) -> bool:
    return path.suffix in {".css", ".njk", ".html"} or (
        path.suffix == ".json" and path.name.startswith("fonts")
    )


@pytest.fixture(scope="session")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the files the check reads, built once; each case copies it again to plant in."""
    root = tmp_path_factory.mktemp("core_template")
    for top in WALKED:
        for here, dirs, names in os.walk(CORE / top):
            dirs[:] = [d for d in dirs if d not in PRUNED]
            for name in names:
                source = Path(here) / name
                if _style_bearing(source):
                    dest = root / source.relative_to(CORE)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
    for name in SIGN_IN_FILES:
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CORE / name, dest)
    return root


@pytest.fixture
def core(template: Path, tmp_path: Path) -> Path:
    copy = tmp_path / "core"
    shutil.copytree(template, copy)
    return copy


def judged(core: Path, allowlist: Path = ALLOWLIST) -> trc.Judgement:
    return trc.judge(trc.find_theme_rules(core), trc.load_allowlist(allowlist))


def triples(items: list[trc.Finding]) -> list[tuple[str, str, str]]:
    return [(f.path, f.key, f.kind) for f in items]


def assert_clean(core: Path, allowlist: Path = ALLOWLIST) -> None:
    result = judged(core, allowlist)
    assert result.ok, (triples(result.new), result.stale, result.count_problems)


def plant(core: Path, relative: str, text: str) -> Path:
    path = core / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------------- the real tree


def test_the_real_tree_passes_with_the_allowlist(capsys: pytest.CaptureFixture[str]) -> None:
    assert trc.main() == 0
    out = capsys.readouterr().out
    assert "theme-rule-check: scanned" in out


def test_the_real_tree_holds_the_rules_the_scouts_read() -> None:
    """The scan reaches each place today's GOV.UK rules are: an empty finding is never blind."""
    found = {f.path for f in trc.find_theme_rules(CORE)}
    assert {
        "packages/design/tokens.css",
        "packages/design/primitives.css",
        "packages/design/panelType.css",
        "packages/design/fonts.json",
        "apps/workspace/src/admin/admin.css",
        "apps/workspace/src/shell/places.css",
        "apps/workspace/src/views/views.css",
        "apps/workspace/src/search/searchResults.css",
        "apps/workspace/src/questions/askPage.css",
        "harness/keycloak_theme.py",
    } <= found


def test_the_allowlist_is_exactly_what_the_check_finds_on_the_real_tree() -> None:
    findings = Counter(f.entry for f in trc.find_theme_rules(CORE))
    listed = trc.load_allowlist(ALLOWLIST)
    assert Counter(listed.entries) == findings
    assert listed.recorded == len(listed.entries) == sum(findings.values())


def test_the_allowlist_header_says_how_it_reaches_zero_and_who_may_lower_it() -> None:
    text = ALLOWLIST.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("count: ")
    lowered = text.lower()
    assert "react gov.uk look" in lowered and "retired" in lowered
    assert "any slice that removes a rule" in lowered
    assert "owner" in lowered and "raise" in lowered
    # No text this slice writes may say a Default build is free of GOV.UK (ADR-152 Am. 4, item 8).
    assert "free of gov.uk" not in lowered and "no gov.uk" not in lowered


# ----------------------------------------------------------------- the seven plants, red then green


def test_i_a_brand_rule_in_the_shared_scale_is_found(
    core: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scale = core / "packages/design/scale.css"
    original = scale.read_text(encoding="utf-8")
    assert_clean(core)
    scale.write_text(original + '\n[data-brand="govuk"] .x { margin: 0; }\n', encoding="utf-8")
    result = judged(core)
    assert triples(result.new) == [("packages/design/scale.css", '[data-brand="govuk"] .x', "rule")]
    assert not result.ok
    # Through the entry point the gate is run by: the file and the rule are named, and it fails.
    assert trc.main(core=core, allowlist_path=ALLOWLIST) == 1
    out = capsys.readouterr().out
    assert "packages/design/scale.css" in out and '[data-brand="govuk"] .x' in out
    scale.write_text(original, encoding="utf-8")
    assert_clean(core)


@pytest.mark.parametrize("family", ['"GDS Transport"', "GDS-Transport", "'gds transport'"])
def test_ii_gds_transport_as_a_font_face_under_the_pages_app_is_found(
    core: Path, family: str
) -> None:
    face = (
        f"@font-face {{ font-family: {family}; font-weight: 700;\n"
        '  src: url("/assets/govuk/bold-affa96571d-v2.woff2") format("woff2"); }\n'
    )
    assert_clean(core)
    where = plant(core, "apps/pages/tree-default/zz_plant.css", face)
    result = judged(core)
    assert triples(result.new) == [
        ("apps/pages/tree-default/zz_plant.css", "@font-face GDS Transport", "font-face")
    ]
    where.unlink()
    assert_clean(core)


def test_ii_a_font_list_entry_naming_gds_transport_under_the_pages_app_is_found(core: Path) -> None:
    entry = (
        '{"fonts": [{"family": "GDS Transport", "role": "govuk", "source": "govuk-frontend",'
        ' "weights": [400, 700], "licence": "restricted"}]}\n'
    )
    plant(core, "apps/pages/fonts.json", entry)
    assert triples(judged(core).new) == [("apps/pages/fonts.json", "GDS Transport", "font-entry")]


def test_iii_a_govuk_rule_in_a_second_themes_folder_is_found(core: Path) -> None:
    plant(
        core,
        "packages/themes/other/tokens.css",
        '[data-brand="govuk"] { --focus: #ffdd00; }\n[data-brand="other"] .x { margin: 0; }\n',
    )
    result = judged(core)
    # The rule of theme `other` is at home there; the GOV.UK rule is not.
    assert triples(result.new) == [
        ("packages/themes/other/tokens.css", '[data-brand="govuk"]', "rule")
    ]


def test_iii_a_second_themes_rule_in_the_govuk_folder_is_found_too(core: Path) -> None:
    plant(core, "packages/themes/govuk/tokens.css", '[data-brand="other"] .x { margin: 0; }\n')
    assert triples(judged(core).new) == [
        ("packages/themes/govuk/tokens.css", '[data-brand="other"] .x', "rule")
    ]


def test_iii_a_govuk_rule_in_a_python_string_in_a_second_themes_folder_is_found(core: Path) -> None:
    plant(
        core,
        "packages/themes/other/sign_in.py",
        'RULES = """\n[data-brand="govuk"] #kc-header { display: none; }\n"""\n',
    )
    assert triples(judged(core).new) == [
        ("packages/themes/other/sign_in.py", '[data-brand="govuk"] #kc-header', "string-rule")
    ]


def test_iv_a_new_govuk_rule_in_a_component_stylesheet_is_found(core: Path) -> None:
    sheet = core / "apps/workspace/src/search/searchResults.css"
    original = sheet.read_text(encoding="utf-8")
    assert_clean(core)
    sheet.write_text(
        original + "\n.search-results--govuk .search-results__zz { margin: 0; }\n", encoding="utf-8"
    )
    result = judged(core)
    assert triples(result.new) == [
        (
            "apps/workspace/src/search/searchResults.css",
            ".search-results--govuk .search-results__zz",
            "rule",
        )
    ]
    sheet.write_text(original, encoding="utf-8")
    assert_clean(core)


def test_iv_a_second_copy_of_an_allowlisted_rule_is_a_new_rule(core: Path) -> None:
    """The real tree repeats a selector (the brand block is in `tokens.css` three times), so a rule
    already on the allowlist, written again, is one more rule and not excused by the first."""
    sheet = core / "apps/workspace/src/search/searchResults.css"
    original = sheet.read_text(encoding="utf-8")
    rule = ".search-results--govuk .search-results__back { margin: 0; }"
    assert rule in original
    sheet.write_text(original + "\n" + rule + "\n", encoding="utf-8")
    result = judged(core)
    assert triples(result.new) == [
        (
            "apps/workspace/src/search/searchResults.css",
            ".search-results--govuk .search-results__back",
            "rule",
        )
    ]


def test_v_an_allowlist_entry_for_a_rule_that_no_longer_exists_is_stale(core: Path) -> None:
    sheet = core / "apps/workspace/src/admin/admin.css"
    original = sheet.read_text(encoding="utf-8")
    rule = ".admin-nav--govuk { width: 220px; }\n"
    assert rule in original
    sheet.write_text(original.replace(rule, ""), encoding="utf-8")  # the rule is removed
    result = judged(core)
    assert result.new == []
    assert result.stale == [("apps/workspace/src/admin/admin.css", ".admin-nav--govuk", "rule")]
    assert not result.ok
    sheet.write_text(original, encoding="utf-8")
    assert_clean(core)


def test_v_an_entry_for_a_file_that_is_gone_is_stale(core: Path) -> None:
    (core / "apps/workspace/src/questions/askPage.css").unlink()
    result = judged(core)
    assert {path for path, _, _ in result.stale} == {"apps/workspace/src/questions/askPage.css"}
    assert result.new == []


def _write_allowlist(path: Path, count: int, entries: list[tuple[str, str, str]]) -> Path:
    lines = [f"count: {count}", "# a test copy"]
    lines += ["\t".join(entry) for entry in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_vi_an_entry_added_without_raising_the_count_fails(core: Path, tmp_path: Path) -> None:
    sheet = core / "apps/workspace/src/search/searchResults.css"
    original = sheet.read_text(encoding="utf-8")
    sheet.write_text(original + "\n.search-results--govuk .zz { margin: 0; }\n", encoding="utf-8")
    real = trc.load_allowlist(ALLOWLIST)
    entry = (
        "apps/workspace/src/search/searchResults.css",
        ".search-results--govuk .zz",
        "rule",
    )
    edited = _write_allowlist(tmp_path / "allow.txt", real.recorded, [*real.entries, entry])
    result = judged(core, edited)
    # The rule is excused by its entry and nothing is stale: only the count says one was added.
    assert result.new == [] and result.stale == []
    assert len(result.count_problems) == 1
    assert "added" in result.count_problems[0]
    assert not result.ok


def test_vi_an_entry_added_with_the_count_raised_with_it_hits_the_ceiling(
    core: Path, tmp_path: Path
) -> None:
    sheet = core / "apps/workspace/src/search/searchResults.css"
    sheet.write_text(
        sheet.read_text(encoding="utf-8") + "\n.search-results--govuk .zz { margin: 0; }\n",
        encoding="utf-8",
    )
    real = trc.load_allowlist(ALLOWLIST)
    entry = ("apps/workspace/src/search/searchResults.css", ".search-results--govuk .zz", "rule")
    edited = _write_allowlist(tmp_path / "allow.txt", real.recorded + 1, [*real.entries, entry])
    result = judged(core, edited)
    assert result.new == [] and result.stale == []
    assert len(result.count_problems) == 1
    assert "ceiling" in result.count_problems[0]


@pytest.mark.parametrize("delta", [-1, 1])
def test_vi_a_recorded_count_that_is_not_the_entry_count_fails(
    core: Path, tmp_path: Path, delta: int
) -> None:
    real = trc.load_allowlist(ALLOWLIST)
    edited = _write_allowlist(tmp_path / "allow.txt", real.recorded + delta, list(real.entries))
    result = judged(core, edited)
    assert result.new == [] and result.stale == []
    assert len(result.count_problems) >= 1
    assert not result.ok


def test_vi_an_entry_and_its_rule_deleted_without_lowering_the_count_fails(
    core: Path, tmp_path: Path
) -> None:
    """The count stays at the ceiling while the list shrinks: only the branch that compares the
    recorded count with the entries held can see it (the ceiling is met, nothing is new or stale),
    so a slice cannot leave headroom for a later entry to be added back unnoticed."""
    sheet = core / "apps/workspace/src/admin/admin.css"
    sheet.write_text(
        sheet.read_text(encoding="utf-8").replace(".admin-nav--govuk { width: 220px; }\n", ""),
        encoding="utf-8",
    )
    real = trc.load_allowlist(ALLOWLIST)
    assert real.recorded == trc.RATCHET_CEILING  # the count is at the ceiling, as it must be
    gone = ("apps/workspace/src/admin/admin.css", ".admin-nav--govuk", "rule")
    entries = list(real.entries)
    entries.remove(gone)
    edited = _write_allowlist(tmp_path / "allow.txt", real.recorded, entries)
    result = judged(core, edited)
    assert result.new == [] and result.stale == []
    assert result.count_problems == [
        f"the allowlist holds {real.recorded - 1} entries but records {real.recorded}: the count "
        "is not the number of entries (it is lowered by deleting an entry's line, and the count "
        "with it)"
    ]
    assert not result.ok


def test_the_count_may_fall_when_an_entry_is_deleted_with_its_rule(
    core: Path, tmp_path: Path
) -> None:
    """The ratchet's good path: a slice removes a rule, deletes its line and lowers the count."""
    sheet = core / "apps/workspace/src/admin/admin.css"
    sheet.write_text(
        sheet.read_text(encoding="utf-8").replace(".admin-nav--govuk { width: 220px; }\n", ""),
        encoding="utf-8",
    )
    real = trc.load_allowlist(ALLOWLIST)
    gone = ("apps/workspace/src/admin/admin.css", ".admin-nav--govuk", "rule")
    entries = list(real.entries)
    entries.remove(gone)
    edited = _write_allowlist(tmp_path / "allow.txt", real.recorded - 1, entries)
    result = judged(core, edited)
    assert result.new == [] and result.stale == []
    # Lower than the ceiling is allowed only if the tool's own ceiling is lowered with it.
    assert result.count_problems == [
        f"the recorded count {real.recorded - 1} is below the ceiling {trc.RATCHET_CEILING}: "
        f"lower RATCHET_CEILING in tools/theme_rule_check.py to {real.recorded - 1}"
    ]


def test_vii_a_rule_inside_the_govuk_theme_folder_for_the_govuk_theme_is_allowed(
    core: Path,
) -> None:
    """The check must not forbid the move it exists to allow (PL12d)."""
    plant(
        core,
        "packages/themes/govuk/tokens.css",
        '[data-brand="govuk"] { --ui: "GDS Transport", arial, sans-serif; --govuk-gutter: 30px; }\n'
        '@media (max-width: 640px) { [data-brand="govuk"] { --govuk-gutter: 15px; } }\n'
        '[data-brand="govuk"] :is(.govuk-header, .govuk-footer) a { border-bottom: 0; }\n'
        '@font-face { font-family: "GDS Transport"; src: url("/assets/govuk/bold.woff2"); }\n',
    )
    plant(
        core,
        "packages/themes/govuk/fonts.json",
        '{"fonts": [{"family": "GDS Transport", "role": "govuk"}]}\n',
    )
    plant(
        core,
        "packages/themes/govuk/sign_in.py",
        'RULES = """\n[data-brand="govuk"] #kc-header { display: none; }\n"""\n',
    )
    assert_clean(core)


def test_vii_a_rule_of_theme_b_inside_its_own_folder_is_allowed_for_any_name(core: Path) -> None:
    plant(core, "packages/themes/other/tokens.css", '[data-brand="other"] { --ui: serif; }\n')
    assert_clean(core)


# ----------------------------------------------------------- the shapes the sign-in theme takes


def test_a_rule_inside_a_python_triple_quoted_string_is_found(core: Path) -> None:
    file = core / "harness/keycloak_theme.py"
    original = file.read_text(encoding="utf-8")
    assert_clean(core)
    file.write_text(
        original
        + '\n\n_ZZ_RULES = """\n[data-brand="govuk"] .zz-plant,\n'
        + '[data-brand="govuk"] #zz { display: none; }\n"""\n',
        encoding="utf-8",
    )
    result = judged(core)
    assert triples(result.new) == [
        (
            "harness/keycloak_theme.py",
            '[data-brand="govuk"] .zz-plant, [data-brand="govuk"] #zz',
            "string-rule",
        )
    ]
    file.write_text(original, encoding="utf-8")
    assert_clean(core)


def test_a_comment_or_a_docstring_naming_a_brand_is_not_a_rule(core: Path) -> None:
    file = core / "harness/keycloak_theme.py"
    original = file.read_text(encoding="utf-8")
    file.write_text(
        original
        + "\n\ndef zz() -> None:\n"
        + '    """A brand is one `[data-brand="govuk"]` block { in tokens.css }."""\n'
        + '    # [data-brand="govuk"] .x { display: none; }\n',
        encoding="utf-8",
    )
    assert_clean(core)


def test_a_rule_in_a_javascript_string_in_the_chrome_script_is_found(core: Path) -> None:
    file = core / "harness/govuk_chrome.js"
    original = file.read_text(encoding="utf-8")
    assert_clean(core)
    file.write_text(
        original
        + '\nvar ZZ = ".govuk-header, .zz { display: none; }";\n// .govuk-footer { x: y }\n',
        encoding="utf-8",
    )
    result = judged(core)
    assert triples(result.new) == [("harness/govuk_chrome.js", ".govuk-header, .zz", "string-rule")]
    file.write_text(original, encoding="utf-8")
    assert_clean(core)


# ------------------------------------------------------------ the scan itself, selector by selector


def found_in(css: str) -> list[tuple[str, str]]:
    return [(f.key, f.kind) for f in trc.css_findings(css)]


def test_a_commented_out_rule_is_not_a_rule() -> None:
    assert found_in('/* [data-brand="govuk"] .x { margin: 0; } */ .y { margin: 0; }') == []


def test_a_brace_or_a_selector_inside_a_string_does_not_end_or_start_a_rule() -> None:
    css = '.a::after { content: "} [data-brand=\\"govuk\\"] .x {"; }\n.b { margin: 0; }\n'
    assert found_in(css) == []


def test_one_theme_name_in_a_selector_list_makes_the_whole_rule_a_theme_rule() -> None:
    assert found_in('.a,\n  [data-brand="govuk"]   .b { margin: 0; }') == [
        ('.a, [data-brand="govuk"] .b', "rule")
    ]


def test_a_rule_in_a_media_block_is_found_and_keyed_with_its_condition() -> None:
    css = (
        "@media (max-width: 640px) "
        '{ [data-brand="govuk"] { --govuk-gutter: 15px; } .a { margin: 0; } }'
    )
    assert found_in(css) == [('@media (max-width: 640px) :: [data-brand="govuk"]', "rule")]


def test_a_modifier_class_and_a_govuk_package_class_are_theme_names() -> None:
    css = (
        ".admin-nav--govuk { width: 1px; } .govuk-places__item { margin: 0; } "
        ".osprey-govuk-top { margin: 0; }"
    )
    assert [k for k, _ in found_in(css)] == [
        ".admin-nav--govuk",
        ".govuk-places__item",
        ".osprey-govuk-top",
    ]


def test_a_word_that_only_contains_the_letters_is_not_a_theme_name() -> None:
    assert found_in(".ungovukable, .govukish, .x { margin: 0; }") == []


def test_a_custom_property_named_for_a_theme_in_a_shared_rule_is_found() -> None:
    assert found_in(":root { --govuk-gutter: 30px; }") == [(":root", "custom-property")]
    assert found_in(".a { padding: var(--govuk-gutter); }") == [(".a", "custom-property")]


def test_a_font_naming_gds_transport_in_a_shared_rule_is_found() -> None:
    assert found_in('.a { font-family: "GDS Transport", arial; }') == [(".a", "font-use")]


def test_a_word_in_a_value_or_a_comment_is_not_a_theme_rule() -> None:
    css = '/* govuk */ .a { content: "govuk"; background: url(/x/govuk.png); }'
    assert found_in(css) == []
    assert found_in('.a::after { content: "--govuk-gutter"; }') == []


def test_a_style_block_in_a_template_is_read_as_a_stylesheet(core: Path) -> None:
    plant(
        core,
        "apps/pages/tree-default/zz_plant.njk",
        '{% extends "layout.njk" %}\n<style>\n[data-brand="govuk"] .zz { margin: 0; }\n</style>\n'
        '<p>[data-brand="govuk"] .not-a-rule { margin: 0; }</p>\n',
    )
    assert triples(judged(core).new) == [
        ("apps/pages/tree-default/zz_plant.njk", '[data-brand="govuk"] .zz', "rule")
    ]


def test_nested_rules_inside_a_theme_rule_are_one_rule_and_inside_another_are_found() -> None:
    css = '[data-brand="govuk"] { .a { margin: 0; } } .b { .govuk-x { margin: 0; } }'
    assert found_in(css) == [('[data-brand="govuk"]', "rule"), (".govuk-x", "rule")]


def test_a_stylesheet_with_a_block_that_never_closes_is_an_error_not_a_pass(
    core: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(trc.ThemeScanError):
        trc.css_findings(".a { margin: 0;")
    plant(core, "apps/pages/tree-default/zz_open.css", '[data-brand="govuk"] .a { margin: 0;')
    assert trc.main(core=core, allowlist_path=ALLOWLIST) == 1
    assert "zz_open.css" in capsys.readouterr().out


# -------------------------------------------------------------------------- what it does not read


@pytest.mark.parametrize(
    "relative",
    [
        "apps/pages/dist/assets/zz.css",
        "apps/pages/node_modules/govuk-frontend/zz.css",
        "apps/workspace/src/public/assets/govuk/govuk-frontend.css",
        "packages/design/node_modules/x/zz.css",
    ],
)
def test_generated_and_installed_output_is_not_scanned(core: Path, relative: str) -> None:
    plant(core, relative, '[data-brand="govuk"] .zz { margin: 0; }\n')
    assert_clean(core)


def test_a_file_outside_the_scan_roots_is_not_scanned(core: Path) -> None:
    plant(core, "services/zz/zz.css", '[data-brand="govuk"] .zz { margin: 0; }\n')
    plant(core, "harness/other.py", 'X = """\n[data-brand="govuk"] .zz { margin: 0; }\n"""\n')
    assert_clean(core)
