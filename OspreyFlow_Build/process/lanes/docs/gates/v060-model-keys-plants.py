"""Red-first plants for the docs lane's model-key correction (v0.6.0, the owner's finding): each planted line at its real call site, one at a time,
on lane/docs-v060-rename; each must turn red the test
named, and the tree is restored by git checkout after each."""
import os, re, subprocess, sys, tempfile
ROOT = sys.argv[1]; PY = sys.argv[2]
UI = "OspreyFlow_Core/apps/workspace/src/"
UG, AG = "OspreyFlow_Core/docs/user-guide.md", "OspreyFlow_Core/docs/administration-guide.md"
TESTS = ["tests/test_admin_guide_model_keys.py"]
PLANTS = [
 ("test_a_key_is_entered_in_admin_models_as_the_guide_says", "Enter key renamed", "OspreyFlow_Core/apps/workspace/src/admin/sections/Models.tsx",
  '"Rotate key" : "Enter key"', '"Rotate key" : "Add key"'),
 ("test_a_key_is_entered_in_admin_models_as_the_guide_says", "Set the key renamed", "OspreyFlow_Core/apps/workspace/src/admin/sections/Models.tsx",
  '"Rotate the key" : "Set the key"', '"Rotate the key" : "Save"'),
 ("test_a_key_is_entered_in_admin_models_as_the_guide_says", "a key offered for an IAM-role engine", "OspreyFlow_Core/apps/workspace/src/admin/sections/Models.tsx",
  '{engine.key_state !== "iam_role" && (', '{true && ('),
 ("test_models_key_runs_the_conduit_s_key_path_and_restarts_nothing", "models key restarts the gateway", "OspreyFlow_Core/cli/ospreyflow/main.py",
  'code, out = ctx.capture([*in_conduit, "api", *engine_keys.KEY_PATH, "status"])', 'ctx.capture([*_compose_of(directory), "restart", "litellm"])\n    code, out = ctx.capture([*in_conduit, "api", *engine_keys.KEY_PATH, "status"])'),
 ("test_the_install_hands_the_key_to_the_gateway_and_removes_its_line", "the key's line kept after the move", "OspreyFlow_Core/harness/apply.py",
  '            line.startswith("OSPREY_MODEL_KEY_") or line.startswith("OSPREY_MODEL_PROVIDER_KEY=")', '            line.startswith("OSPREY_UNUSED_")'),
 ("test_the_guide_s_old_words_are_gone_both_copies", "the old sentence back in the Core copy", "OspreyFlow_Core/docs/administration-guide.md",
  "**From the command line**, for headless use", "A key is kept in `deployment.env` alone. **From the command line**, for headless use"),
 ("test_the_guide_s_old_words_are_gone_both_copies", "the old CLI row back in spec/10", "OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md",
  "the key is kept by the model gateway alone, and nothing is restarted.", "writes it to `deployment.env` alone and restarts the model gateway."),
 ("test_a_key_is_entered_in_admin_models_as_the_guide_says", "the guide: no Admin › Models", "OspreyFlow_Core/docs/administration-guide.md",
  "**On a running deployment, a key is entered in Admin › Models**", "**On a running deployment, a key is given at the command line**"),
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
