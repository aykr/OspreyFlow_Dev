"""Red-first plants for the docs lane's §6a.9 Bedrock in London (v0.6.0, the owner's ruling 17): each planted line at its real call site, one at a time,
on lane/docs-v060-rename; each must turn red the test
named, and the tree is restored by git checkout after each."""
import os, re, subprocess, sys, tempfile
ROOT = sys.argv[1]; PY = sys.argv[2]
UI = "OspreyFlow_Core/apps/workspace/src/"
UG, AG = "OspreyFlow_Core/docs/user-guide.md", "OspreyFlow_Core/docs/administration-guide.md"
TESTS = ["tests/test_admin_guide_bedrock_london.py"]
PLANTS = [
 ("test_the_example_is_a_model_the_schema_admits_and_london_serves", "the guide's old Claude example back", "OspreyFlow_Core/docs/administration-guide.md",
  "roles: {extraction: amazon.nova-pro-v1:0}", "roles: {extraction: anthropic.claude-3-haiku-20240307-v1:0}"),
 ("test_the_example_is_a_model_the_schema_admits_and_london_serves", "spec/10's example an EU profile", "OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md",
  "roles: {extraction: amazon.nova-pro-v1:0}", "roles: {extraction: eu.amazon.nova-pro-v1:0}"),
 ("test_the_example_is_a_model_the_schema_admits_and_london_serves", "the schema admits only one provider's ids", "OspreyFlow_Core/packages/schemas/deployment.py",
  '_BEDROCK_MODEL_ID = re.compile(r"[a-z0-9-]+\\.[^.\\s:]+(:[^.\\s]+)?")', '_BEDROCK_MODEL_ID = re.compile(r"cohere\\.[^.\\s:]+(:[^.\\s]+)?")'),
 ("test_the_guide_says_what_bedrock_in_london_means", "the London sentence gone", "OspreyFlow_Core/docs/administration-guide.md",
  "Claude through AWS's EU profile is not offered in v0.6.0.**", "**"),
 ("test_the_guide_says_what_bedrock_in_london_means", "the old not-yet-tried line back", "OspreyFlow_Core/docs/administration-guide.md",
  "(current Claude models are not among the models here:", "; newer Claude models are offered in London only through inference profiles (current Claude models are not among the models here:"),
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
