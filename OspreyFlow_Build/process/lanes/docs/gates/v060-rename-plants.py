"""Red-first plants for the docs lane's v0.6.0 rename (item 9): each planted line at its real call site, one at a time,
on lane/docs-v060-rename merged with platform's lane/platform-v060-fresh-only (rf); each must turn red the test
named, and the tree is restored by git checkout after each."""
import os, re, subprocess, sys, tempfile
ROOT = sys.argv[1]; PY = sys.argv[2]
UI = "OspreyFlow_Core/apps/workspace/src/"
UG, AG = "OspreyFlow_Core/docs/user-guide.md", "OspreyFlow_Core/docs/administration-guide.md"
TESTS = ["tests/test_guides_v060_fresh.py", "tests/test_guide_6a_upgrade.py", "tests/test_guides_release_header.py",
         "tests/harness/test_poc_manifest.py", "tests/test_guides_step5_freeze.py", "tests/test_guides_v051_gaps.py"]
PLANTS = [
 ("test_the_changelog_says_v060_is_installed_fresh_and_version_names_it", "VERSION back at v0.5.2", "OspreyFlow_Core/VERSION",
  "v0.6.0", "v0.5.2"),
 ("test_the_tables_are_printed_from_the_manifest_alone", "the manifest left at v0.5.2", "OspreyFlow_Core/harness/cloud_platform/poc_manifest.yaml",
  "\nversion: v0.6.0\n", "\nversion: v0.5.2\n"),
 ("test_the_changelog_says_v060_is_installed_fresh_and_version_names_it", "the CHANGELOG without the fresh-install sentence", "OspreyFlow_Core/CHANGELOG.md",
  "**v0.6.0 is installed fresh: there is no upgrade to it from any earlier version.**\n\n", ""),
 ("test_the_changelog_says_v060_is_installed_fresh_and_version_names_it", "the CHANGELOG's Before you update back", "OspreyFlow_Core/CHANGELOG.md",
  "**Before you install.**", "**Before you update.**"),
 ("test_every_guide_s_header_names_the_latest_release", "the user guide's header left at v0.5.2", "OspreyFlow_Core/docs/user-guide.md",
  "· For OspreyFlow v0.6.0 · Issued", "· For OspreyFlow v0.5.2 · Issued"),
 ("test_the_guides_say_how_a_v060_deployment_moves_and_that_v060_is_installed_fresh", "§14 without its opening rule", "OspreyFlow_Core/docs/administration-guide.md",
  "**v0.6.0 is installed fresh.** No earlier deployment is moved to it:", "No earlier deployment is moved to it:"),
 ("test_the_guides_say_how_a_v060_deployment_moves_and_that_v060_is_installed_fresh", "the README without its line", "OspreyFlow_Core/README.md",
  "v0.6.0 itself is installed fresh: no earlier deployment is moved to it,", "No earlier deployment is moved,"),
 ("test_section_14_quotes_the_refusal_as_harness_fresh_only_words_it", "§14's quotation in other words", "OspreyFlow_Core/docs/administration-guide.md",
  "and nothing moves it onto v0.6.0.", "and it is not moved onto v0.6.0."),
 ("test_section_14_quotes_the_refusal_as_harness_fresh_only_words_it", "rf's words changed at their source", "OspreyFlow_Core/harness/fresh_only.py",
  "is installed fresh; this deployment is", "is a fresh install; this deployment is"),
 ("test_no_guide_keeps_a_passage_for_an_earlier_release_s_deployment", "a struck passage put back in §13", "OspreyFlow_Core/docs/administration-guide.md",
  "**v0.6.0 is installed fresh.**", "Sets taken before v0.5.0 may still be in the checkout's `backups/`. **v0.6.0 is installed fresh.**"),
 ("test_no_guide_keeps_a_passage_for_an_earlier_release_s_deployment", "the named-volume move put back in the README", "OspreyFlow_Core/README.md",
  "v0.6.0 itself is installed fresh:", "The stores' one-time move to named volumes runs first. v0.6.0 itself is installed fresh:"),
 ("test_v060_is_said_to_be_installed_fresh_and_the_move_not_rehearsed", "§6a.1's old install test put back", "OspreyFlow_Core/docs/administration-guide.md",
  "**Not yet rehearsed.** No deployment has yet been moved to a new release by these steps:", "**What will check it.** It is to install v0.5.1, then the candidate by these steps over it:"),
 ("test_v060_is_said_to_be_installed_fresh_and_the_move_not_rehearsed", "§6a.1 without its v0.6.0 line", "OspreyFlow_Core/docs/administration-guide.md",
  "v0.6.0 itself is installed fresh, into a namespace of its own: a namespace on an earlier release stays on it (section 14). ", ""),
 ("test_an_update_rebuilds_the_index_inside_what_rolls_back", "§14's old index sentence put back", "OspreyFlow_Core/docs/administration-guide.md",
  "rebuilds the search index from the graph. If anything fails", "rebuilds the search index from the graph (an index made before v0.5.2 is not one v0.5.2 writes to). If anything fails"),
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
