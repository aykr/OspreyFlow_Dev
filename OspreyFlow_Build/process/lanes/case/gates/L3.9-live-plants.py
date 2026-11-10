"""L3.9's live plants (rule 15): each live check planted out at its own call site, its live test run
against the leased stack, the file restored. Run from the worktree root, under the lease, with the
stack's ports exported: `python3 OspreyFlow_Build/process/lanes/case/gates/L3.9-live-plants.py <out>`."""
import os, pathlib, subprocess, sys

CORE = pathlib.Path("OspreyFlow_Core")
T = "../OspreyFlow_Build/tests/services/api/"
PLANTS = [
    ("the merged drawing left out of its case's read set", "services/api/datasets.py",
     '        return list(dict.fromkeys([*held, *(r["dataset_id"] for r in drawn)]))',
     "        return held", T + "test_datasets_store.py", "merges_a_drawn_dataset"),
    ("the case not moved onto the target", "services/api/datasets.py",
     '            if moved != "UPDATE 1":\n                raise DrawnAlreadyMerged(merged.dataset_id)',
     "            pass", T + "test_datasets_store.py", "merges_a_drawn_dataset"),
    ("the trigger check never widened", "services/api/promotion_store.py",
     "        AND c.contype = 'c' AND pg_get_constraintdef(c.oid) LIKE '%drawn_merge%'",
     "        AND c.contype = 'c'", T + "test_promotion_store.py", "old_trigger_check"),
    ("the matches' edges never written back", "services/api/promotion_store.py",
     '                [(promotion_id, n, e) for n, e in enumerate(edge_ids)],',
     '                [(promotion_id, -1, e) for n, e in enumerate(edge_ids)],',
     T + "test_promotion_store.py", "drawn_merge_and_its_matches"),
    ("a drawn merge's copies not written with its record (Amendment 7)",
     "services/api/promotion_store.py",
     "            if copies:\n                await _insert_copies(conn, record.id, copies)\n",
     "", T + "test_promotion_store.py", "copies_are_written_with_it"),
    ("the record and its copies written outside one transaction",
     "services/api/promotion_store.py",
     '        async with self._pool.acquire() as conn, conn.transaction():\n            await conn.execute(\n                f"INSERT INTO promotions',
     '        async with self._pool.acquire() as conn:\n            await conn.execute(\n                f"INSERT INTO promotions',
     T + "test_promotion_store.py", "copies_are_refused_is_not_written"),
    ("the copies' ids never written back", "services/api/promotion_store.py",
     "                [(promotion_id, n, w, same) for n, (w, same) in enumerate(written)],",
     "                [(promotion_id, -1, w, same) for n, (w, same) in enumerate(written)],",
     T + "test_promotion_store.py", "copies_are_written_with_it"),
    ("a waiting merge's copies read for the grading change",
     "services/api/promotion_store.py",
     "    \"WHERE p.status = 'committed' AND c.written_id IS NOT NULL ORDER BY c.kind, c.written_id\"",
     "    \"WHERE c.written_id IS NOT NULL ORDER BY c.kind, c.written_id\"",
     T + "test_promotion_store.py", "committed_merges_written_copies"),
    ("a board's lens not rewritten", "services/api/case_views.py",
     "                await self._rewrite(conn, _merged(board, load_id, drawn.get(board.id, ())))",
     "                pass", T + "test_case_views_store.py", "boards_into_views"),
]
out = []
for words, f, old, new, test, k in PLANTS:
    p = CORE / f
    src = p.read_text()
    assert src.count(old) == 1, (words, src.count(old))
    p.write_text(src.replace(old, new))
    try:
        r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", test, "-q",
                            "-p", "no:cacheprovider", "-k", k], cwd=CORE, capture_output=True, text=True)
    finally:
        p.write_text(src)
    tail = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "E  ")) or " passed" in l or " failed" in l][:6]
    out.append(f"## {words}\nplant in {f}; {test} -k {k}; exit {r.returncode} ({'RED' if r.returncode else 'NOT CAUGHT'})\n" + "\n".join(tail) + "\n")
pathlib.Path(sys.argv[1]).write_text("\n".join(out))
print("\n".join(l for l in out if l.startswith("##") or "exit" in l))
