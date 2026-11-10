"""L3.6's offline plants (rule 15): each check planted out at its own call site, its test run, the
file restored. Run from the worktree root: `python3 OspreyFlow_Build/process/lanes/case/gates/
L3.6-plants.py <out>`."""
import os, pathlib, subprocess, sys

CORE = pathlib.Path("OspreyFlow_Core")
W = "../OspreyFlow_Build/tests/services/api/test_drawn_watch_alerts.py"
B = "../OspreyFlow_Build/tests/services/api/test_boards.py"
Q = "../OspreyFlow_Build/tests/services/api/test_drawn_watch_queue.py"
PLANTS = [
  ("a link type requiring a property offered and drawn",
   "services/api/boards.py",
   "            if any(p.required for p in held.properties):\n                continue\n",
   "", B, "requires_a_property"),
  ("a match raised again on every load (no claim)",
   "services/api/drawn_watches.py",
   "            if not await self.items.claim_match(watch, node.id, now):\n                continue  # one alert per match per case",
   "            await self.items.claim_match(watch, node.id, now)",
   W, "one_alert_per_match or each_case_gets"),
  ("the loaded nodes read above the owner (the handling filter not theirs)",
   "services/api/drawn_watches.py",
   "            sorted(set(node_ids)), owner.model_copy(update={\"datasets\": [dataset_id]})",
   "            sorted(set(node_ids)), owner.model_copy(update={\"datasets\": [dataset_id], \"clearance\": \"SECRET\"})",
   W, "owner_may_not_see or counted_by_what"),
  ("a watch run for a case that reads the dataset no more",
   "services/api/drawn_watches.py",
   "        if dataset_id not in read_set:\n            return 0  # the case reads that dataset no more",
   "        if False:\n            return 0",
   W, "reads_the_dataset_no_more"),
  ("a pair decided on the board raised all the same",
   "services/api/drawn_watches.py",
   "            if node.id in decided:\n                continue\n",
   "", W, "decided_on_the_board"),
  ("a drawn node taken for a loaded one",
   "services/api/drawn_watches.py",
   "            and node.provenance.drawn is None\n",
   "", W, "unalike_of_another_type_or_drawn"),
  ("a watch run for an owner gone",
   "services/api/drawn_watches.py",
   "        owner = await self.owner_of(watch.owner)\n        if owner is None:\n            return 0",
   "        owner = await self.owner_of(watch.owner) or Principal(id=watch.owner, clearance=\"SECRET\", org_unit=\"unit-1\")",
   W, "owner_gone"),
  ("a node of another type taken as alike",
   "services/api/boards.py",
   "    if loaded.type != drawn.type or drawn.provenance.drawn is None:\n        return None",
   "    if drawn.provenance.drawn is None:\n        return None",
   W, "unalike_of_another_type_or_drawn"),
  ("the drawn item left out of the alert's evidence (shown to a reader who may not see it)",
   "services/api/drawn_watches.py",
   "        referent_node_ids=[drawn.id, loaded.id],",
   "        referent_node_ids=[loaded.id],",
   Q, "drawn_item_the_reader_may_not_see"),
  ("the loaded node left out of the alert's evidence",
   "services/api/drawn_watches.py",
   "        referent_node_ids=[drawn.id, loaded.id],",
   "        referent_node_ids=[drawn.id],",
   Q, "loaded_node_the_reader_may_not_see"),
]
env = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994")
out = []
for words, f, old, new, test, k in PLANTS:
    p = CORE / f
    src = p.read_text()
    assert src.count(old) == 1, (words, src.count(old))
    p.write_text(src.replace(old, new))
    try:
        r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", test, "-q", "-p", "no:cacheprovider", "-k", k], cwd=CORE, env=env, capture_output=True, text=True)
    finally:
        p.write_text(src)
    lines = r.stdout.splitlines()
    tail = [l for l in lines if l.startswith("FAILED") or " passed" in l or " failed" in l]
    tail += [l for l in lines if l.startswith("E  ")][:3]
    out.append(f"## {words}\nplant in {f}; -k {k}; exit {r.returncode}\n" + "\n".join(tail) + "\n")
    print(words, "->", "RED" if r.returncode else "GREEN (plant not caught!)")
r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", W, B, Q, "-q", "-p", "no:cacheprovider"], cwd=CORE, env=env, capture_output=True, text=True)
out.append("## restored\n" + r.stdout.strip().splitlines()[-1] + "\n")
pathlib.Path(sys.argv[1]).write_text("\n".join(out))
