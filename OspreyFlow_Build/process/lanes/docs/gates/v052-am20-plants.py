"""Run from the repository root on a clean tree: python3 OspreyFlow_Build/process/lanes/docs/gates/v052-am20-plants.py

v052-am20's red-first run: main's guides first, then each plant at its real call site in the code or in the
guide's own sentence, one at a time; the test that holds it must be red. Each run with a fresh PYTHONPYCACHEPREFIX."""
import os, re, subprocess, sys, tempfile
from pathlib import Path

#: The repository root, from this file's own place: process/lanes/docs/gates/ under OspreyFlow_Build.
WT = str(Path(__file__).resolve().parents[5])
PY = f"{WT}/OspreyFlow_Core/.venv/bin/python"
CACHES = tempfile.mkdtemp(prefix="v052-am20-pycache-")
os.makedirs(CACHES, exist_ok=True)
TESTS = ["tests/test_user_guide_am20.py", "tests/test_admin_guide_model_timeouts.py", "tests/test_guides_step5_freeze.py"]
env = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994")
for k in ("OSPREY_LANE", "PYTHONDONTWRITEBYTECODE"): env.pop(k, None)
C, W = "OspreyFlow_Core/", "OspreyFlow_Core/apps/workspace/src/"
AG, UG, DG, ARG = (f"{C}docs/{n}-guide.md" for n in ("administration", "user", "developer", "architecture"))
SITES = "OspreyFlow_Build/marketing_site/sites/build.py"
GUIDES = {AG, UG, DG, ARG}
PLANTS = [
    ("the chunk made 50,000", C + "packages/adapters/graph_arcadedb/adapter.py", "_ID_CHUNK = 1000", "_ID_CHUNK = 50000", ["found_a_thousand_records_at_a_time"]),
    ("the ids written into the query again", C + "packages/adapters/graph_arcadedb/adapter.py", "            query = render_edges_among_gremlin(rids, self._access, principal, edge_types)\n", "            query = render_edges_among_gremlin(chunk, self._access, principal, edge_types)\n", ["found_a_thousand_records_at_a_time"]),
    ("the builder's literal id list back", C + "packages/adapters/graph_arcadedb/builders.py", "    has_access = access.gremlin_has_step(principal)\n    label_filter", "    has_access = access.gremlin_has_step(principal) + f'.has(\"id\", within({list(record_ids)}))'\n    label_filter", ["found_a_thousand_records_at_a_time"]),
    ("the batch job's links read another way", C + "services/api/batch_expansion.py", "    links = await graph.edges_among(node_ids, scoped) if len(node_ids) > 1 else []", "    links = []", ["what_a_user_sees_reads_edges_among"]),
    ("a view's links read another way", C + "services/api/case_views.py", "    edges = await graph.edges_among([n.id for n in nodes], principal) if len(nodes) > 1 else []", "    edges = []", ["what_a_user_sees_reads_edges_among"]),
    ("guide: the line struck", UG, "The links among the records are found a thousand records at a time,", "The links among the records are found,", ["what_a_user_sees_reads_edges_among"]),
    # D2: how long a model is waited for
    ("the client's hosted default 60", C + "packages/adapters/model_litellm/client.py", 'os.environ.get("OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS", "120")', 'os.environ.get("OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS", "60")', ["render_and_the_client_agree"]),
    ("the deployment's own model counted as hosted", C + "packages/adapters/model_litellm/client.py", "hosted = call is not None and call.engine != LOCAL", "hosted = call is not None", ["render_and_the_client_agree"]),
    ("the timeout's words reworded", C + "packages/adapters/model_litellm/errors.py", 'f"{engine} did not answer within the time this deployment allows{bound}, so the "', 'f"{engine} timed out{bound}, so the "', ["timeout_and_a_refusal"]),
    ("nothing recorded struck", C + "packages/adapters/model_litellm/errors.py", '        return f"{said} Nothing was recorded."', '        return said', ["timeout_and_a_refusal"]),
    ("a timeout raised as a failure", C + "packages/adapters/model_litellm/client.py", 'raise ModelEngineRefused("timed_out", timeout_seconds=self._bound()) from None', "raise", ["timeout_and_a_refusal"]),
    ("guide: the hosted bound 60", AG, "is waited for 120 seconds, `OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS`", "is waited for 60 seconds, `OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS`", ["section_10_gives_both_bounds"]),
    ("guide: nothing recorded struck", AG, "with the bound; nothing is recorded.", "with the bound.", ["timeout_and_a_refusal"]),
    ("the render's hosted default 60", C + "harness/render.py", '    "OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS": "120",', '    "OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS": "60",', ["render_and_the_client_agree", "section_10_gives_both_bounds"]),
    ("compose no longer passing them", C + "harness/render.py", '            for name, seconds in MODEL_TIMEOUTS.items():\n                api_environment[name] = "${" + name + ":-" + seconds + "}"\n', "", ["render_and_the_client_agree"]),
    ("a cluster without them", C + "harness/cluster.py", "    for name, seconds in MODEL_TIMEOUTS.items():\n        environment.setdefault(name, seconds)\n", "", ["cluster_and_the_platform_render_both"]),
    ("a setting for them in osprey.yaml", C + "packages/schemas/deployment.py", "class SearchBackend(StrEnum):", "#: hosted_timeout_seconds: a model call's bound\nclass SearchBackend(StrEnum):", ["cluster_and_the_platform_render_both"]),
    ("guide: the platform said to pass neither", AG, "the render puts both settings in the values at their defaults", "the render passes neither setting, so the defaults hold", ["cluster_and_the_platform_render_both"]),
    # R7 after case's S7 and S8: the mark asks why, and is read back
    ("the mark asking nothing", W + "canvas/GlassCanvas.tsx", '        why: "Why should it be suppressed? (required, kept with the mark)",\n', "", ["what_a_suppression_mark_does"]),
    ("a blank reason accepted", C + "services/api/app.py", '        if not value.strip():\n            raise ValueError("a suppression mark needs a reason")\n', "", ["what_a_suppression_mark_does"]),
    ("the marks not read back", W + "canvas/GlassCanvas.tsx", "if (live && Array.isArray(marks)) setSuppressionMarks(Object.fromEntries(marks.map((m) => [m.node_id, m.reason])));", "if (live && Array.isArray(marks)) void marks;", ["what_a_suppression_mark_does"]),
    ("removing asking why too", W + "canvas/GlassCanvas.tsx", "      if (suppressionMarks[nodeId]) {\n        await writeSuppressionMark(nodeId, null, anchor);\n        return;\n      }\n", "", ["what_a_suppression_mark_does"]),
    ("guide: the mark said to keep no reason", UG, 'It asks first "Why should it be suppressed?", which is required and kept with the mark;', "It asks nothing;", ["what_a_suppression_mark_does"]),
    ("guide: the marks said not read back", UG, "The marks are read back from the case, so on a marked node the menu offers **Remove suppression mark** in its place, which asks nothing.", "After a reload the menu offers the mark again.", ["what_a_suppression_mark_does"]),
]
def run():
    e = dict(env, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(dir=CACHES))
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *TESTS], cwd=f"{WT}/OspreyFlow_Build", env=e, capture_output=True, text=True)
    failed = re.findall(r"^FAILED \S+?::(.+?)(?: - .*)?$", r.stdout, re.M)
    summary = next((l for l in r.stdout.splitlines()[::-1] if " passed" in l or " failed" in l or "error" in l), r.stdout[-300:])
    return failed, summary
def apply(path, old, new):
    full = f"{WT}/{path}"; s = open(full).read()
    if path in GUIDES:
        pat = r"\s+".join(map(re.escape, old.split())); n = len(re.findall(pat, s)); assert n == 1, (path, old, n)
        s = re.sub(pat, lambda m: new, s, count=1)
    else:
        assert s.count(old) == 1, (path, old, s.count(old)); s = s.replace(old, new)
    open(full, "w").write(s)
if "--check" in sys.argv:
    bad = []
    for l, p, o, n, w in PLANTS:
        s = open(f"{WT}/{p}").read()
        c = len(re.findall(r"\s+".join(map(re.escape, o.split())), s)) if p in GUIDES else s.count(o)
        if c != 1: bad.append((l, c))
    print(bad or "every plant found once"); sys.exit(bool(bad))
assert subprocess.run(["git", "-C", WT, "status", "--porcelain"], capture_output=True, text=True).stdout == "", "commit first"
print("command: cd OspreyFlow_Build && python -m pytest -q -p no:cacheprovider", " ".join(TESTS))
print("each run: closed ports 59991-59994, no OSPREY_LANE, a fresh PYTHONPYCACHEPREFIX\n")
for path in [AG, UG, DG, ARG, SITES]:
    subprocess.run(["git", "-C", WT, "show", f"main:{path}"], stdout=open(f"{WT}/{path}", "w"), check=True)
failed, summary = run()
subprocess.run(["git", "-C", WT, "checkout", "--", AG, UG, DG, ARG, SITES], check=True)
print(f"== main's four guides and the sites' build.py, before this branch: {summary}\n   red: {', '.join(failed)}\n")
ok = len(failed) > 0
for label, path, old, new, want in PLANTS:
    apply(path, old, new)
    failed, summary = run()
    subprocess.run(["git", "-C", WT, "checkout", "--", path], check=True)
    missing = [w for w in want if not any(w in f for f in failed)]
    ok &= not missing
    gone = [l.strip() for l in old.splitlines() if l.strip() and l not in new.splitlines()] or [old.strip()]
    came = [l.strip() for l in new.splitlines() if l.strip() and l not in old.splitlines()] or ["(removed)"]
    print(f"== {label} [{path.rsplit('/', 1)[-1]}]\n   - " + "\n   - ".join(repr(l[:150]) for l in gone) + "\n   + " + "\n   + ".join(repr(l[:150]) for l in came) + f"\n   {summary}\n   red: {', '.join(failed) or 'none'}" + (f"\n   <-- NOT red: {missing}" if missing else "") + "\n")
failed, summary = run()
print(f"== restored: {summary}")
print("each plant red in the tests that hold it:", ok and not failed)
sys.exit(0 if ok and not failed else 1)
