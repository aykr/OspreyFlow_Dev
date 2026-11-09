import subprocess, sys, os, pathlib
CORE = pathlib.Path("OspreyFlow_Core")
T = "../OspreyFlow_Build/tests/services/api/test_drawn_merge.py"
PLANTS = [
  ("the Author check removed (targets() takes every home case's dataset)",
   "services/api/drawn_merge.py",
   "            if await self.promotions.is_author_of(dataset_id, reader):\n                out[dataset_id] = dataset",
   "            out[dataset_id] = dataset",
   "no_author_of_the_target"),
  ("merge_datasets removed from the routes",
   "services/api/app.py",
   "_MERGES = [Depends(require_right(Right.MERGE_DATASETS))]",
   "_MERGES: list[Any] = []",
   "names_merge_datasets"),
  ("the match candidates read unscoped (the target scope dropped)",
   "services/api/drawn_merge.py",
   "            reader.model_copy(update={\"datasets\": [target.id]}),\n            self._read_as",
   "            reader.model_copy(update={\"datasets\": None}),\n            self._read_as",
   "no_match_is_offered"),
  ("the target's highest marking check removed (`_problems`'s marking)",
   "services/api/promotions.py",
   "            if not self.boards.scheme.clears(highest, marking):\n                problems.append((",
   "            if False:\n                problems.append((",
   "above_the_targets_highest"),
  ("a chosen match not checked against what is offered",
   "services/api/drawn_merge.py",
   "            if pick not in offered or pick[0] not in going:",
   "            if pick[0] not in going:",
   "not_offered_is_refused"),
  ("the dry run merges",
   "services/api/drawn_merge.py",
   "        goes, left, rows = await self._plan(drawn, case_id, target, body, reader)\n        return DrawnMergeDryRun(",
   "        await self.merge(drawn, case_id, target, body, reader)\n        goes, left, rows = await self._plan(drawn, case_id, target, body, reader)\n        return DrawnMergeDryRun(",
   "dry_run_counts"),
  ("a match written asserted (rule 5)",
   "services/api/drawn_merge.py",
   "                    state=ProvenanceState.INFERRED,",
   "                    state=ProvenanceState.ASSERTED,",
   "becomes_a_view"),
  ("the boards left as boards (decision 7)",
   "services/api/drawn_merge.py",
   "        await self.views.merge_boards(record.case_id, record.load_id, drawn)",
   "        pass",
   "becomes_a_view"),
  ("annotations read unfiltered (the reader's clearance dropped)",
   "services/api/drawn_merge.py",
   "    elements: dict[str, Any] = {n.id: n for n in await graph.get_nodes(node_ids, reader)}",
   "    reader = reader.model_copy(update={\"clearance\": \"SECRET\"})\n    elements: dict[str, Any] = {n.id: n for n in await graph.get_nodes(node_ids, reader)}",
   "annotation_is_withheld"),
  ("committed at once whatever the policy",
   "services/api/drawn_merge.py",
   "        if promotions.commits_at_once(target):\n            return await promotions._commit(record, by=None)\n        return record\n\n\n@dataclass",
   "        return await promotions._commit(record, by=None)\n\n\n@dataclass",
   "second_person"),
  ("the revert leaving the merge's matches live",
   "scripts/revert_promotion.py",
   "        if drawn_merge:\n            await merge.undo_writes(record, tx)",
   "        pass",
   "reverting_a_merge"),
  ("the revert leaving the case on the target and its views",
   "scripts/revert_promotion.py",
   "    if drawn_merge:\n        await merge.undo(record)",
   "    pass",
   "reverting_a_merge"),
  ("the revert taking no stores for a drawn merge",
   "scripts/revert_promotion.py",
   "    if drawn_merge and merge is None:",
   "    if False:",
   "reverting_a_merge"),
]
env = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994")
out = []
for words, f, old, new, k in PLANTS:
    p = CORE / f
    src = p.read_text()
    assert src.count(old) == 1, (words, src.count(old))
    p.write_text(src.replace(old, new))
    try:
        r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", T, "-q", "-p", "no:cacheprovider", "-k", k], cwd=CORE, env=env, capture_output=True, text=True)
    finally:
        p.write_text(src)
    tail = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "E  ")) or " passed" in l or " failed" in l][:8]
    out.append(f"## {words}\nplant in {f}; -k {k}; exit {r.returncode}\n" + "\n".join(tail) + "\n")
    print(words, "->", "RED" if r.returncode else "GREEN (plant not caught!)")
r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", T, "-q", "-p", "no:cacheprovider"], cwd=CORE, env=env, capture_output=True, text=True)
out.append("## restored\n" + r.stdout.strip().splitlines()[-1] + "\n")
pathlib.Path(sys.argv[1]).write_text("\n".join(out))
