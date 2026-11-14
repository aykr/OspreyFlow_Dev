"""Red-first plants for the docs lane's saved-views tests: each planted line at its real call site, one at a time, on
the docs branch merged with case's lane/case-saved-views and case-b's ViewsPanel.tsx; each must turn red the test
named, and the tree is restored by git checkout after each."""
import os, re, subprocess, sys, tempfile
ROOT = sys.argv[1]; PY = sys.argv[2]
UI = "OspreyFlow_Core/apps/workspace/src/"
UG, AG = "OspreyFlow_Core/docs/user-guide.md", "OspreyFlow_Core/docs/administration-guide.md"
TESTS = ["tests/test_user_guide_saved_views.py", "tests/test_user_guide_navigation.py", "tests/test_guide_navigation_words.py"]
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
 ("test_the_canvas_notice_and_the_one_way_to_saved_views", "the canvas notice reworded", UI+"canvas/GlassCanvas.tsx",
  "Go back to the whole case to change it.", "Go back to the case to change it."),
 ("test_the_canvas_notice_and_the_one_way_to_saved_views", "the case line's button while unread", UI+"shell/ContextBanner.tsx",
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
  "offering **Open the whole case** while one is", "offering nothing while one is"),
 ("test_view_means_a_saved_view_in_every_guide_and_in_the_glass", "the admin guide: More views", AG,
  "view switch, under **More**, or in", "view switch, under **More views**, or in"),
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
    pat = r"\s+".join(map(re.escape, old.split())) if path.endswith(".md") else re.escape(old)
    n = len(re.findall(pat, s)); assert n >= 1, (label, n)
    open(p, "w", encoding="utf-8").write(re.sub(pat, lambda m: new, s, count=1))
    out, failed = run()
    subprocess.run(["git", "checkout", "--", path], cwd=ROOT, check=True)
    red = any(f.startswith(test) for f in failed)
    bad += not red
    lines.append(f"{'RED ' if red else 'MISS'} {label}\n     {path}: {old!r} -> {new!r}\n     failed: {', '.join(failed) or 'none'}")
out, failed = run(); lines.append(f"restored: {out.strip().splitlines()[-1]}"); bad += bool(failed)
print("\n".join(lines)); sys.exit(1 if bad else 0)
