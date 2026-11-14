"""Step 3h (ADR-124 Amendment 19: clusters per reader, nothing shared carries a cluster id): each test's red, a plant
at the real call site, the old shared path planted back whole among them.

Run from the worktree root at the commit under test, nothing else changed:
    python3 OspreyFlow_Build/process/lanes/case/gates/merged_clusters_reds.py > OspreyFlow_Build/process/lanes/case/gates/merged-clusters-reds.<head>.log

Each plant replaces exact strings in files (refused if one is not there exactly once), runs the named test (pytest on
the closed ports with no lane, vitest, or Playwright on the lane's slot 2), records the result and restores every file
with `git checkout`. A plant whose test stays green is a failure of this record.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
CORE = ROOT / "OspreyFlow_Core"
BUILD = ROOT / "OspreyFlow_Build"
WS = CORE / "apps/workspace"
SERVICE = "OspreyFlow_Core/services/api/working_set/service.py"
TESTS = "tests/services/api/working_set/test_merged_clusters.py"
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994", "OPENSEARCH_PORT": "59999"}

# (what, [(file from the root, old, new)], runner, test file, test name)
PLANTS = [
    ("an add's own clusters left off its answer",
     [(SERVICE, "clusters = DeltaReproject(seq=delta.seq, reason=REASON_ENTRY, affected_cluster_ids=ids)", "clusters = None")],
     "pytest", TESTS, "test_a_pair_already_merged_at_the_cases_threshold_arrives_with_a_shared_cluster_id"),
    ("the walk not reaching the members already on the canvas",
     [(SERVICE, "                frontier = reached - members\n", "                frontier = set()\n")],
     "pytest", TESTS, "test_the_second_member_seeded_alone_joins_the_first_already_on_the_canvas"),
    ("an add's clusters put on the shared stream",
     [(SERVICE, "                clusters = DeltaReproject(seq=delta.seq, reason=REASON_ENTRY, affected_cluster_ids=ids)\n",
       "                clusters = DeltaReproject(seq=delta.seq, reason=REASON_ENTRY, affected_cluster_ids=ids)\n                await self._store.append_delta(investigation_id, clusters)\n")],
     "pytest", TESTS, "test_the_clusters_go_on_the_readers_own_response_never_the_shared_stream_or_store"),
    ("the old shared path: the actor's ids on the shared stream, and passed on with the keys a reader may read",
     [(SERVICE, "        await self._store.append_delta(\n            investigation_id, DeltaReproject(seq=seq, reason=REASON_THRESHOLD, affected_cluster_ids={})\n        )\n",
       "        await self._store.append_delta(\n            investigation_id, DeltaReproject(seq=seq, reason=REASON_THRESHOLD, affected_cluster_ids=delta_counts.affected_cluster_ids)\n        )\n"),
      (SERVICE, "                affected_cluster_ids={},\n            )\n        # No rule for it",
       "                affected_cluster_ids={k: v for k, v in delta.affected_cluster_ids.items() if k in (known or {}) and principal_may_read((known or {})[k].handling, (known or {})[k].datasets, principal, self._scheme)},\n            )\n        # No rule for it")],
     "pytest", TESTS, "test_another_readers_threshold_move_gives_no_cluster_id_through_a_member_this_one_may_not_see"),
    ("a cluster id stored before the amendment sent on",
     [(SERVICE, "    if node.resolution.cluster_id is None:\n        return node\n", "    if True:\n        return node\n")],
     "pytest", TESTS, "test_a_cluster_id_stored_before_the_amendment_reaches_no_reader"),
    ("explain reading a cluster from the stored nodes again",
     [(SERVICE, "        clusters = await self._reader_clusters(investigation_id, principal)\n        candidate_ids = {node_id for node_id, cluster in clusters.items() if cluster == cluster_id}\n",
       "        nodes_by_id = await self._store.source_fidelity_nodes(investigation_id)\n        candidate_ids = {n for n, node in nodes_by_id.items() if node.resolution.cluster_id == cluster_id}\n")],
     "pytest", "tests/services/api/working_set/test_manual_resolution.py", "test_explain_cluster_returns_the_direct_edges_between_current_members"),
    ("the snapshot without the reader's own clusters",
     [(SERVICE, "        visible_nodes = _with_clusters(visible_nodes, await self._reader_clusters(investigation_id, principal))\n", "")],
     "pytest", "tests/services/api/working_set/test_resolution_threshold.py", "test_msisdn_and_imsi_endpoints_cluster_together_the_device_does_not"),
    ("the client dropping the clusters a seed answers with",
     [("OspreyFlow_Core/apps/workspace/src/workingset/models.ts", "return outcome.clusters ? [outcome.delta, outcome.clusters] : [outcome.delta];", "return [outcome.delta];")],
     "jsdom", "src/connections/connectionsApi.test.ts", "hands back the reader's own clusters after the add"),
    ("the canvas not applying an expansion's clusters",
     [("OspreyFlow_Core/apps/workspace/src/canvas/GlassCanvas.tsx", "      for (const delta of outcomeDeltas(outcome as ExpansionOutcome)) store.getState().applyDelta(delta);\n",
       "      store.getState().applyDelta(outcome.delta);\n")],
     "browser", "keyboard/canvas-clusters-on-entry.spec.ts", "Explain cluster is offered on a pair already merged"),
    ("a reader's own clusters taken for a change of the resolution (the folds opened)",
     [("OspreyFlow_Core/apps/workspace/src/canvas/GlassCanvas.tsx", '      if (lastReproject?.reason === "resolution_on_entry") return;\n', "")],
     "browser", "keyboard/canvas-clusters-on-entry.spec.ts", "a fold made from a same-as link stays folded"),
]


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    if subprocess.run(["git", "status", "--porcelain", "--", "OspreyFlow_Core", "OspreyFlow_Build/tests"], capture_output=True, text=True, cwd=ROOT).stdout.strip():
        print("refused: the tree has uncommitted changes; plants restore with git checkout")
        return 2
    print(f"# merged-clusters reds at {head}; each plant restored with `git checkout -- <files>`")
    stayed = 0
    for n, (what, edits, runner, test_file, name) in enumerate(PLANTS, 1):
        bad = [(f, (ROOT / f).read_text().count(o)) for f, o, _ in edits if (ROOT / f).read_text().count(o) != 1]
        if bad:
            print(f"## {n}. {what}\nrefused: a planted string is not there exactly once: {bad}")
            stayed += 1
            continue
        for f, o, nw in edits:
            (ROOT / f).write_text((ROOT / f).read_text().replace(o, nw))
        try:
            if runner == "pytest":
                cmd = [str(CORE / ".venv/bin/python"), "-m", "pytest", "-p", "no:cacheprovider", "-q", f"{test_file}::{name}"]
                env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | CLOSED
                cwd = BUILD
            elif runner == "jsdom":
                cmd, env, cwd = ["npx", "vitest", "run", test_file, "-t", name], os.environ, WS
            else:
                cmd = ["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", test_file, "-g", re.escape(name), "--workers=1"]
                env, cwd = {**os.environ, "OSPREY_PORTS_SLOT": "2"}, WS
            run = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)
        finally:
            subprocess.run(["git", "checkout", "--", *sorted({f for f, _, _ in edits})], check=True, cwd=ROOT)
        out = run.stdout + run.stderr
        lines = [l for l in out.splitlines() if any(k in l for k in ("×", "✘", "AssertionError", "assert ", "Error:", "FAILED", "Expected", "Received", " passed", " failed"))]
        print(f"## {n}. {what}\nplant in {', '.join(sorted({f for f, _, _ in edits}))}; {' '.join(cmd[-4:])}; exit {run.returncode}")
        print("\n".join(lines[:12]))
        if run.returncode == 0:
            stayed += 1
            print("STAYED GREEN")
        elif not re.search(r"\d+ failed|FAILED|×|✘", out):
            stayed += 1
            print("NO TEST FAILED (the run failed otherwise): not a red")
    print(f"# {len(PLANTS) - stayed} of {len(PLANTS)} red")
    return 1 if stayed else 0


if __name__ == "__main__":
    sys.exit(main())
