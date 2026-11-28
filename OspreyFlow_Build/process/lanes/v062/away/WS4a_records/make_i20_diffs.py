"""WS4a: the owner's wiring diffs for I20, made from scratch copies of the protected files (nothing in the tree edited)."""
import difflib
import pathlib

REPO = pathlib.Path.home() / "away-ws4a"
OUT = REPO / "OspreyFlow_Build/process/lanes/v062/away/WS4a_diffs"
OUT.mkdir(parents=True, exist_ok=True)


#: Each file's text after the diffs made so far: a later diff of the same file applies on top of the earlier ones (I20's
#: first, then the comparison's), so the owner applies them in the order they were made.
APPLIED: dict[str, str] = {}


def diff(rel: str, name: str, subs: list[tuple[str, str]]) -> None:
    before = APPLIED.get(rel) or (REPO / rel).read_text()
    after = before
    for old, new in subs:
        assert after.count(old) == 1, (rel, old)
        after = after.replace(old, new)
    APPLIED[rel] = after
    text = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{rel}", f"b/{rel}"))
    (OUT / f"{name}.diff").write_text(text)


diff("OspreyFlow_Core/Makefile", "I20_CORE_MAKEFILE", [
    (".PHONY: check lint typecheck no-react-check version-isolation-check ",
     ".PHONY: check lint typecheck no-react-check version-isolation-check same-drawing-versions-check "),
    ("check: lint typecheck no-react-check version-isolation-check ",
     "check: lint typecheck no-react-check version-isolation-check same-drawing-versions-check "),
    ("version-isolation-check:\n\tnode scripts/version_isolation_check.mjs\n",
     "version-isolation-check:\n\tnode scripts/version_isolation_check.mjs\n\n"
     "# ADR-152 I20 (ADR-002 Amendment 1): both front ends resolve the same versions of sigma, @sigma/*, maplibre-gl and\n"
     "# graphology in package-lock.json, except a difference written in apps/pages/VERSION_WINDOW.yaml with the day it\n"
     "# opened. Shown red then green by the developer repository's tests/glass_trees/test_same_drawing_versions.py (slice\n"
     "# WS4a). The release paths run it with --release, which refuses while the window lists anything.\n"
     "same-drawing-versions-check:\n\tnode scripts/same_drawing_versions_check.mjs\n"),
])

diff(".github/workflows/ci.yml", "I20_CI", [
    ("      - run: node scripts/version_isolation_check.mjs\n",
     "      - run: node scripts/version_isolation_check.mjs\n"
     "      # ADR-152 I20: the same drawing versions in both front ends, or a difference written in the version window.\n"
     "      - run: node scripts/same_drawing_versions_check.mjs\n"),
])

diff("OspreyFlow_Build/tools/release_local.py", "I20_RELEASE_LOCAL", [
    ("existing cases in `tests/test_release_owed.py` assert and which are unchanged.\n\"\"\"",
     "existing cases in `tests/test_release_owed.py` assert and which are unchanged.\n\n"
     "**No release while the version window is open** (ADR-002 Amendment 1, item 3; ADR-152 I20): while\n"
     "`apps/pages/VERSION_WINDOW.yaml` lists anything, the two front ends may resolve different versions of a renderer,\n"
     "and no release is cut. `scripts/same_drawing_versions_check.mjs --release` refuses then, in words naming each\n"
     "entry; it is asked last of the four, before anything is built.\n\"\"\""),
    ("def owed_refusal() -> str | None:",
     "#: ADR-152 I20 at release: the same drawing versions, and the version window empty.\n"
     "SAME_VERSIONS = REPO_ROOT / \"scripts\" / \"same_drawing_versions_check.mjs\"\n\n\n"
     "def window_refusal() -> str | None:\n"
     "    \"\"\"Why a release must wait for the version window to close, in the check's words, or None when it is shut.\"\"\"\n"
     "    p = subprocess.run([\"node\", str(SAME_VERSIONS), str(REPO_ROOT), \"--release\"], capture_output=True, text=True,\n"
     "                       check=False)  # fmt: skip\n"
     "    return None if p.returncode == 0 else (p.stdout + p.stderr).strip()\n\n\n"
     "def owed_refusal() -> str | None:"),
    ("    refusal = register_refusal()\n    if refusal:\n        print(f\"release_local: refusing — {refusal}\", file=sys.stderr)\n        return 1\n",
     "    refusal = register_refusal()\n    if refusal:\n        print(f\"release_local: refusing — {refusal}\", file=sys.stderr)\n        return 1\n"
     "    refusal = window_refusal()\n    if refusal:\n"
     "        print(f\"release_local: refusing — the version window is open:\\n{refusal}\", file=sys.stderr)\n"
     "        return 1\n"),
])

diff("OspreyFlow_Build/scripts/publish_user_repo_update.sh", "I20_PUBLISH", [
    ("make -C \"$ROOT/ospreyflow/OspreyFlow_Build\" publish-user-repo",
     "# No release while the version window is open (ADR-002 Amendment 1, item 3; ADR-152 I20): the check release_local.py asks.\n"
     "(cd \"$ROOT/ospreyflow/OspreyFlow_Core\" && node scripts/same_drawing_versions_check.mjs . --release) \\\n"
     "  || { echo \"STOP: the version window is open, or the front ends differ (above); nothing was published.\" >&2; exit 1; }\n"
     "make -C \"$ROOT/ospreyflow/OspreyFlow_Build\" publish-user-repo"),
])
# The canvas-look comparison's wiring (WS4a): its own step in CI's Glass job and its own Makefile target, written once
# a CI run has shown it green on CI's runner (question 2 of the report).
diff("OspreyFlow_Core/Makefile", "COMPARE_CORE_MAKEFILE", [
    (" glass-perf glass-a11y glass-keyboard ", " glass-perf glass-a11y glass-keyboard glass-canvas-compare "),
    ("glass-keyboard:\n\tnpm run test:keyboard --workspace apps/workspace\n",
     "glass-keyboard:\n\tnpm run test:keyboard --workspace apps/workspace\n\n"
     "# ADR-152 decision 9: the canvas-look comparison WS4 is held to (`apps/workspace/keyboard/canvas-compare.spec.ts`),\n"
     "# each scene's whole canvas against its reference within one pixel tolerance. Its references belong to one WebGL\n"
     "# renderer (`keyboard/canvas-compare/REFERENCES.json`); on another it says so and fails.\n"
     "glass-canvas-compare:\n\tnpm run test:canvas-compare --workspace apps/workspace\n"),
])
diff(".github/workflows/ci.yml", "COMPARE_CI", [
    ("      - run: npm run test:keyboard --workspace apps/workspace\n",
     "      - run: npm run test:keyboard --workspace apps/workspace\n"
     "      # ADR-152 decision 9: the canvas-look comparison (WS4a). Its references were made with SwiftShader; this step\n"
     "      # is added once a run here has shown it green (or the references are made here, the owner's choice).\n"
     "      - run: npm run test:canvas-compare --workspace apps/workspace\n"),
])
print("written", sorted(p.name for p in OUT.iterdir()))
