"""Red-first plants for the docs lane's saved-views tests: each planted line at its real call site, one at a time, on
the docs branch merged with case's lane/case-saved-views and case-b's ViewsPanel.tsx; each must turn red the test
named, and the tree is restored by git checkout after each."""
import os, re, subprocess, sys, tempfile
ROOT = sys.argv[1]; PY = sys.argv[2]
UI = "OspreyFlow_Core/apps/workspace/src/"
UG, AG = "OspreyFlow_Core/docs/user-guide.md", "OspreyFlow_Core/docs/administration-guide.md"
TESTS = ["tests/test_user_guide_saved_views.py", "tests/test_user_guide_navigation.py", "tests/test_guide_navigation_words.py",
         "tests/test_guides_no_client_words.py"]
PLANTS = [
 ("test_the_strip_starts_with_the_way_back", "the strip's note in its old words", UI+"views/ViewLensBanner.tsx",
  "Nothing in a saved view changes the case.", "Nothing in a view changes the case."),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "the strip's note in its old words (old names)", UI+"views/ViewLensBanner.tsx",
  "Nothing in a saved view changes the case.", "Nothing in a view changes the case."),
 ("test_the_strip_starts_with_the_way_back", "the strip's focus not taken", UI+"views/ViewLensBanner.tsx",
  "useEffect(() => strip.current?.focus(), []);", "useEffect(() => undefined, []);"),
 ("test_the_list_starts_with_the_whole_case_and_tells_default_named_views_apart", "the second line's separator", UI+"views/ViewsPanel.tsx",
  "`${view.first_item} · saved ${when}`", "`${view.first_item}, saved ${when}`"),
 ("test_the_list_starts_with_the_whole_case_and_tells_default_named_views_apart", "no Open the whole case", UI+"views/ViewsPanel.tsx",
  'aria-label="Open the whole case"', 'aria-label="Back to the case"'),
 ("test_the_canvas_notice_and_the_toolbar", "the canvas notice reworded", UI+"canvas/GlassCanvas.tsx",
  "Go back to the whole case to change it.", "Go back to the case to change it."),
 ("test_sections_3_and_5_give_the_case_line_as_the_banner_draws_it", "the case line's button while unread", UI+"shell/ContextBanner.tsx",
  ': "Saved views";', ': "Views in this case";'),
 ("test_sections_3_and_5_give_the_case_line_as_the_banner_draws_it", "the open saved view not on the case line", UI+"shell/ContextBanner.tsx",
  "› Saved view: {openView}", "{openView}"),
 ("test_section_5_names_the_view_switch_and_more_views_in_order", "More back to More views", UI+"shell/railLayout.ts",
  'export const MORE_LABEL = "More";', 'export const MORE_LABEL = "More views";'),
 ("test_the_views_the_guides_name_are_where_the_layout_puts_them", "More back to More views (the admin guide)", UI+"shell/railLayout.ts",
  'export const MORE_LABEL = "More";', 'export const MORE_LABEL = "More views";'),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "the over-cap dialog's old words", UI+"workingset/ViewOverCapDialog.tsx",
  "delete it from Saved views.", "delete it from Views in this case."),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "the toolbar's Views menu drawn again", UI+"canvas/ViewActions.tsx",
  "Clear the graph", "Clear the graph<ViewsMenu />"),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "Clear view on screen", UI+"canvas/ViewActions.tsx",
  "Clear the graph", "Clear view"),
 ("test_the_strip_starts_with_the_way_back", "the guide: the way back last", UG,
  "The strip above the graph starts with **Back to the whole case**", "The strip above the graph ends with **Back to the whole case**"),
 ("test_sections_3_and_5_give_the_case_line_as_the_banner_draws_it", "the guide: the old case line", UG,
  "Case ‹name› ▾ · Saved views (n) · reads", "Case ‹name› ▾ · Views in this case · reads"),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "the guide: the old case line (old names)", UG,
  "Case ‹name› ▾ · Saved views (n) · reads", "Case ‹name› ▾ · Views in this case · reads"),
 ("test_the_list_starts_with_the_whole_case_and_tells_default_named_views_apart", "the guide: no Open the whole case", UG,
  "offering **Open** (*Open the whole case*, to a screen reader) while one is", "offering nothing while one is"),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "the admin guide: More views", AG,
  "view switch, under **More**, or in", "view switch, under **More views**, or in"),
 ("test_the_user_guide_names_the_composition_its_scale_and_the_measure_as_the_glass_does", "the composition's label back to Client parity", UI+"strength/words.ts",
  'client_parity: "Rarity plus adds",', 'client_parity: "Client parity",'),
 ("test_the_user_guide_names_the_composition_its_scale_and_the_measure_as_the_glass_does", "the measure's label with (the client's)", UI+"strength/words.ts",
  'share: "share of pair links",', 'share: "share of pair links (the client\'s)",'),
 ("test_the_user_guide_names_the_composition_its_scale_and_the_measure_as_the_glass_does", "the Inspector's scale back to the client's", UI+"inspector/StrengthExplained.tsx",
  'aria-label="Raw sum on the raw-sum scale"', 'aria-label="Raw sum on the client\'s scale"'),
 ("test_no_guide_says_the_client_s_words", "the guide: the influencers' note back", UG,
  "its count would. Boosts add up.", 'its count would, and are marked "to be confirmed with the client". Boosts add up.'),
 ("test_no_guide_says_the_client_s_words", "the guide: client parity in the table", UG,
  "| **Rarity plus adds** | rarity plus", "| **Client parity** | rarity plus"),
 ("test_the_user_guide_names_the_composition_its_scale_and_the_measure_as_the_glass_does", "the guide: client parity in the table (its label)", UG,
  "| **Rarity plus adds** | rarity plus", "| **Client parity** | rarity plus"),
 ("test_the_developer_guide_s_note_example_is_no_setting_still_to_be_confirmed", "the developer guide: the old note example", "OspreyFlow_Core/docs/developer-guide.md",
  "    note: set from the 2026 calibration", "    note: to be confirmed with the client"),
 ("test_no_guide_says_the_client_s_words", "the developer guide: the old note example (old words)", "OspreyFlow_Core/docs/developer-guide.md",
  "    note: set from the 2026 calibration", "    note: to be confirmed with the client"),
 ("test_the_strip_starts_with_the_way_back", "the strip's way back moved after its note, in the real file", UI+"views/ViewLensBanner.tsx",
  [("        Back to the whole case\n      </button>", "      </button>"),
   ("Nothing in a saved view changes the case.</span>", "Nothing in a saved view changes the case.</span><button>Back to the whole case</button>")], None),
 ("test_the_app_draws_the_strip_the_panel_and_the_way_back", "the drawer titled Cases from the case line", UI+"App.tsx",
  'title={casesOpen === "views" ? "Saved views" : "Cases"}', 'title="Cases"'),
 ("test_the_app_draws_the_strip_the_panel_and_the_way_back", "the whole case's Open not wired", UI+"App.tsx",
  "onOpenWholeCase={() => {", "onSomethingElse={() => {"),
 ("test_the_app_draws_the_strip_the_panel_and_the_way_back", "the whole-case strip not drawn", UI+"App.tsx",
  "<WholeCaseStrip />}", "null}"),
 ("test_the_app_draws_the_strip_the_panel_and_the_way_back", "focus not returned to Saved views", UI+"App.tsx",
  "requestAnimationFrame(() => focusSavedViewsButton());", "requestAnimationFrame(() => undefined);"),
 ("test_the_app_draws_the_strip_the_panel_and_the_way_back", "the alert's words", UI+"App.tsx",
  'label: "Opened from an alert",', 'label: "From an alert",'),
 ("test_the_list_starts_with_the_whole_case_and_tells_default_named_views_apart", "the open view offers Open", UI+"views/ViewsPanel.tsx",
  "{!isOpen && (", "{true && ("),
 ("test_the_list_starts_with_the_whole_case_and_tells_default_named_views_apart", "the Glass's default name changed", UI+"canvas/GlassCanvas.tsx",
  "return `Selection of ${n} node", "return `Chosen: ${n} node"),
 ("test_the_canvas_notice_and_the_toolbar", "Clear the graph renamed", UI+"canvas/ViewActions.tsx",
  "            Clear the graph", "            Empty the graph"),
 ("test_sections_3_and_5_give_the_case_line_as_the_banner_draws_it", "the case line's open saved view after the button", UI+"shell/ContextBanner.tsx",
  [("{openView && <span className=\"context-banner__open-view\">› Saved view: {openView}</span>}", ""),
   ("{savedViewsLabel(savedViews)}", "{savedViewsLabel(savedViews)}{openView && <span>› Saved view: {openView}</span>}")], None),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "the demo guide: More views again", "OspreyFlow_Core/DEMO_GUIDE.md",
  "under *More* (so named since ADR-145 Amendment 17);", "under *More views*;"),
 ("test_the_views_the_guides_name_are_where_the_layout_puts_them", "the admin guide: the Reports view again", AG,
  "**In the Glass**, **Reports** (the top bar's view switch) draws", "**In the Glass**, the **Reports** view (the top bar's view switch) draws"),
 ("test_the_app_draws_the_strip_the_panel_and_the_way_back", "the decision: the only-route claim again", "OspreyFlow_Build/spec/06_DECISIONS.md",
  "is the one route on the case's own screen to its saved", "is the one route to a case's saved"),
 ("test_the_app_draws_the_strip_the_panel_and_the_way_back", "the guide: the one way again", UG,
  "on the case's own screen it is the one route to them, and the **Cases** panel, from **All cases**, still lists each case's saved views.", "it is the one way to them."),
]
def run():
    env = dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.mkdtemp())
    out = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *TESTS], cwd=f"{ROOT}/OspreyFlow_Build", env=env, capture_output=True, text=True).stdout
    return out, [m.group(1) for m in re.finditer(r"^FAILED \S+?::(.+?)(?: - .*)?$", out, re.MULTILINE)]
assert subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout == "", "a clean tree"
lines, bad = [], 0
out, failed = run(); summary = out.strip().splitlines()[-1]
lines.append(f"unplanted: {summary}"); bad += bool(failed)
for test, label, path, old, new in PLANTS:
    p = f"{ROOT}/{path}"; s = open(p, encoding="utf-8").read()
    for o, nw in (old if isinstance(old, list) else [(old, new)]):
        pat = r"\s+".join(map(re.escape, o.split())) if path.endswith(".md") else re.escape(o)
        n = len(re.findall(pat, s)); assert n >= 1, (label, o, n)
        s = re.sub(pat, lambda m: nw, s, count=1)
    open(p, "w", encoding="utf-8").write(s)
    out, failed = run()
    subprocess.run(["git", "checkout", "--", path], cwd=ROOT, check=True)
    red = any(f.startswith(test) for f in failed)
    bad += not red
    shown = "; ".join(f"{o!r} -> {nw!r}" for o, nw in (old if isinstance(old, list) else [(old, new)]))
    lines.append(f"{'RED ' if red else 'MISS'} {label}\n     {path}: {shown}\n     failed: {', '.join(failed) or 'none'}")
out, failed = run(); lines.append(f"restored: {out.strip().splitlines()[-1]}"); bad += bool(failed)
print("\n".join(lines)); sys.exit(1 if bad else 0)
