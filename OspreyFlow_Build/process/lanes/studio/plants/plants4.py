"""Part A2's plants aimed at second_run, third_run, third_said and coming_back; each restored by md5."""
import hashlib, os, re, subprocess, sys, time
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parents[5]
CORE = str(ROOT / "OspreyFlow_Core")
BUILD = str(ROOT / "OspreyFlow_Build")
RUN = f"{CORE}/services/api/recipe_run.py"
PUB = f"{CORE}/services/api/studio_publish.py"
APP = f"{CORE}/services/api/app.py"
SCOPE = f"{CORE}/services/api/dataset_scope.py"
LIVE = "tests/services/api/test_snapshot_withdrawal_tells_nothing_live.py"
SCHED = "tests/services/api/test_studio_load_stamps_its_case_dataset_live.py"
ROUTE = "tests/services/api/test_studio_run_now_stamps_its_case_dataset_live.py"
FINISH = "    await deps.recipe_runs.finish(run_id, report=report, now=datetime.now(UTC))\n"
OTHERS = '''    async with deps.recipe_runs._pool.acquire() as _c:  # plant: other cases' kept rows of these keys
        _n = int(await _c.fetchval(
            "SELECT count(*) FROM loaded_row_keys WHERE recipe_id = $1 AND investigation_id <> $2 "
            "AND row_key = ANY($3::text[])", report.recipe_id, investigation_id, _keys) or 0)
'''
W = ("    _keys = list(report.withdrawn_row_keys)\n" + OTHERS +
     "    await deps.recipe_runs.finish(run_id, report=report.model_copy(update={'rows_read': report.rows_read + _n}), now=datetime.now(UTC))\n")
X = ("    _keys = sorted(await deps.recipe_runs.withdrawn_row_keys_among(report.recipe_id, investigation_id, report.kept_row_keys))\n" + OTHERS +
     "    await deps.recipe_runs.finish(run_id, report=report.model_copy(update={'rows_read': report.rows_read + _n}), now=datetime.now(UTC))\n")
NOTE = "                await _note_rows_back_unrevertable(recipe, report, sink, investigation_scope)\n"
BACK = '''                _back = sorted(await sink.withdrawn_row_keys_among(recipe.id, investigation_scope, report.kept_row_keys))
                async with sink._ledger._pool.acquire() as _c:  # plant: other cases' kept rows of the returning keys
                    _n = int(await _c.fetchval(
                        "SELECT count(*) FROM loaded_row_keys WHERE recipe_id = $1 AND investigation_id <> $2 "
                        "AND row_key = ANY($3::text[])", recipe.id, investigation_scope, _back) or 0)
'''
Y = NOTE + BACK + "                if _n:\n                    report.refresh_notes = [*report.refresh_notes, f'{_n} other']\n"
Z = NOTE + BACK + ('''                _links = sorted({e for k in _back if (el := report.kept_row_elements.get(k)) for e in el.edge_ids})
                if _n and _links:  # plant: whenever another case keeps the key
                    await graph.withdraw_elements([], _links, report.load_id, tx)
''')
PLANTS = {
    "W": ("second_run: the withdrawal run's ledger row counts other cases' kept rows of the dropped keys", RUN, FINISH, W, [LIVE]),
    "X": ("third_run: the returning run's ledger row counts other cases' kept rows of the returning keys", RUN, FINISH, X, [LIVE]),
    "Y": ("third_said: the returning run's words count other cases' kept rows of the returning keys", PUB, NOTE, Y, [LIVE]),
    "Z": ("coming_back: a returning row's link withdrawn when another case keeps the same key", PUB, NOTE, Z, [LIVE]),
    "U": ("the raw adapter in place of the stamping graph (as Part A's test drove it)",
          f"{BUILD}/{SCHED}", "    graph = stamping(raw)\n    graph.check_against(stores.datasets)\n    return graph\n",
          "    return raw\n", [SCHED, ROUTE]),
    "V": ("scope_to_case taken out of the scheduler's check_case", APP,
          "        return await scope_to_case(owner, case, state.datasets)\n\n    async def run(\n",
          "        return owner\n\n    async def run(\n", [SCHED]),
    "T": ("scope_to_case taken out of get_principal", APP,
          "    return await scope_to_case(identity, investigation_id, get_datasets(request))\n",
          "    return identity\n", [ROUTE]),
}
SCHEDULER = f"{CORE}/services/api/scheduler.py"
TICK = "tests/services/api/test_studio_load_stamps_its_case_dataset_live.py::test_one_tick_stamps_each_scheduled_run_with_its_own_cases_dataset"
SHARED = "tests/services/api/test_studio_load_stamps_its_case_dataset_live.py::test_two_cases_loading_into_one_dataset_read_one_link_and_a_third_reads_none"
RUNS_PY = f"{CORE}/services/api/recipe_runs.py"
CHUNK = "tests/services/api/test_row_key_withdrawal_ledger.py::test_withdrawn_row_keys_among_reads_more_keys_than_one_statement_holds"
MULTI = {
    "S1": ("owners resolved for every due recipe before any runs (the refactor the stamp's order forbids)", SCHEDULER, [
        ("        for recipe in await self.recipes.scheduled():\n            try:\n                await self._consider(",
         "        self._pre = {r.recipe_id: await self._owner(r) for r in await self.recipes.scheduled()}\n"
         "        for recipe in await self.recipes.scheduled():\n            try:\n                await self._consider("),
        ("        try:\n            owner, case = await self._owner(recipe)\n        except _Refused as refused:\n            await self._not_run(",
         "        try:\n            owner, case = getattr(self, '_pre', {}).get(recipe.recipe_id) or await self._owner(recipe)\n        except _Refused as refused:\n            await self._not_run("),
    ], [TICK]),
    "S2": ("Run now's stamp kept, its confinement dropped (get_principal scopes the stamp, returns the unconfined identity)", APP, [
        ("    return await scope_to_case(identity, investigation_id, get_datasets(request))\n",
         "    await scope_to_case(identity, investigation_id, get_datasets(request))\n    return identity\n"),
    ], [ROUTE]),
    "F": ("the unit fake's withdrawn_row_keys_among ignoring the case", f"{BUILD}/tests/ingest/test_snapshot_withdrawal.py", [
        ("            if k[:2] == (recipe_id, case) and k[2] in set(keys)\n",
         "            if k[0] == recipe_id and k[2] in set(keys)\n"),
    ], ["tests/services/api/test_row_key_withdrawal_ledger.py::test_the_unit_files_fake_moves_keys_as_the_ledger_does"]),
    "C1": ("withdrawn_row_keys_among unchunked: one ANY of every key", RUNS_PY, [
        ('            for start in range(0, len(unique), _KEY_CHUNK):\n                rows = await conn.fetch(\n                    "SELECT row_key FROM withdrawn_row_keys', '            for start in range(0, 1):\n                rows = await conn.fetch(\n                    "SELECT row_key FROM withdrawn_row_keys'),
        ('                    unique[start : start + _KEY_CHUNK],\n                )\n                found.update(', '                    unique,\n                )\n                found.update('),
    ], [CHUNK]),
    "C2": ("withdrawn_row_keys_among stopping after one chunk", RUNS_PY, [
        ('            for start in range(0, len(unique), _KEY_CHUNK):\n                rows = await conn.fetch(\n                    "SELECT row_key FROM withdrawn_row_keys', '            for start in range(0, min(len(unique), 1), _KEY_CHUNK):\n                rows = await conn.fetch(\n                    "SELECT row_key FROM withdrawn_row_keys'),
    ], [CHUNK]),
    "S3": ("scope_to_case stamps the case's dataset but confines nobody", SCOPE, [
        ('    return principal.model_copy(update={"datasets": datasets})\n',
         '    return principal.model_copy(update={"datasets": None})\n'),
    ], [SHARED]),
}
env = {**os.environ, "OSPREY_LANE": "studio", "ARCADEDB_HTTP_PORT": "2491", "POSTGRES_PORT": "55433",
       "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "6379", "CLICKHOUSE_HTTP_PORT": "18123"}
for letter in sys.argv[1:]:
    if letter in MULTI:
        name, path, pairs, tests = MULTI[letter]
    else:
        name, path, old, new, tests = PLANTS[letter]
        pairs = [(old, new)]
    orig = open(path).read(); digest = hashlib.md5(orig.encode()).hexdigest()
    planted = orig
    for old, new in pairs:
        assert planted.count(old) == 1, (letter, planted.count(old), old[:60])
        planted = planted.replace(old, new)
    t0 = time.strftime("%H:%M:%SZ", time.gmtime())
    try:
        open(path, "w").write(planted)
        out = subprocess.run([f"{CORE}/.venv/bin/pytest", "-q", "-p", "no:cacheprovider", *tests],
                             cwd=BUILD, env=env, capture_output=True, text=True).stdout
    finally:
        open(path, "w").write(orig)
        assert hashlib.md5(open(path).read().encode()).hexdigest() == digest
    summary = [l for l in out.splitlines() if re.search(r"\d+ (passed|failed|error)", l)]
    failed = [l.split("::")[-1] for l in out.splitlines() if l.startswith(("FAILED", "ERROR"))]
    firsts = [l for l in out.splitlines() if l.startswith("E   ")][:2]
    print(f"## {letter}: {name} ({t0})\nrun: {summary[-1] if summary else out[-600:]}\nfailed: {failed}\nfirst: {firsts}\nrestored md5 {digest}\n", flush=True)
