"""Red-first plants for the docs lane's user guide §6, an answer's items (v0.6.0 item 5): each planted line at its real call site, one at a time,
on lane/docs-v060-ask-items merged with case's lane/case-v060-show-all; each must turn red the test
named, and the tree is restored by git checkout after each."""
import os, re, subprocess, sys, tempfile
ROOT = sys.argv[1]; PY = sys.argv[2]
UI = "OspreyFlow_Core/apps/workspace/src/"
UG, AG = "OspreyFlow_Core/docs/user-guide.md", "OspreyFlow_Core/docs/administration-guide.md"
TESTS = ["tests/test_user_guide_ask_items.py"]
PLANTS = [
 ("test_the_two_actions_and_when_each_is_offered", "Save offered for links alone", "OspreyFlow_Core/apps/workspace/src/questions/AnswerActions.tsx",
  "const canSave = onSaveAsView !== undefined && ids.nodeIds.length > 0;", "const canSave = onSaveAsView !== undefined;"),
 ("test_the_two_actions_and_when_each_is_offered", "Show all on graph renamed", "OspreyFlow_Core/apps/workspace/src/questions/AnswerActions.tsx",
  "            Show all on graph", "            Put all on the graph"),
 ("test_what_show_all_cannot_show_is_a_count_and_past_the_limit_nothing", "what is not shown, said in other words", "OspreyFlow_Core/apps/workspace/src/questions/showAnswer.ts",
  "of this answer's items could not be shown.", "items were hidden from you."),
 ("test_what_show_all_cannot_show_is_a_count_and_past_the_limit_nothing", "a saved view left open", "OspreyFlow_Core/apps/workspace/src/App.tsx",
  "    if (lens) closeLens();\n    results.leave();", "    results.leave();"),
 ("test_save_as_a_view_names_the_view_as_the_code_does", "the view named otherwise", "OspreyFlow_Core/apps/workspace/src/questions/AnswerActions.tsx",
  '"Answer from Ask & Chat"', '"An answer"'),
 ("test_save_as_a_view_names_the_view_as_the_code_does", "the saved message changed", "OspreyFlow_Core/apps/workspace/src/App.tsx",
  "Open it from Saved views.`);", "Find it in Saved views.`);"),
 ("test_save_as_a_view_names_the_view_as_the_code_does", "the case line's count not raised", "OspreyFlow_Core/apps/workspace/src/App.tsx",
  "    setViewsRead((n) => n + 1);\n    setToast(`Saved as a view:", "    setToast(`Saved as a view:"),
 ("test_the_two_actions_and_when_each_is_offered", "the guide: links alone offer Save too", "OspreyFlow_Core/docs/user-guide.md",
  "An answer whose markers stand for links alone offers only **Show all on graph**.", "Every answer offers both."),
 ("test_what_show_all_cannot_show_is_a_count_and_past_the_limit_nothing", "the guide names what it cannot show", "OspreyFlow_Core/docs/user-guide.md",
  "), never which.", "), each named."),
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
