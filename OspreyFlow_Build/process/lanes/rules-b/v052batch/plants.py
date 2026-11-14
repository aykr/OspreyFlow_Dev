"""rules-b v052batch's offline plants (rule 15, ADR-151): each protection removed at its real call
site in `services/api/batch_expansion.py`, and the tests that name it run with a fresh bytecode cache;
then the file restored and the whole module run as a control. Run from OspreyFlow_Core with the
closed offline ports. The route's Editor gate and the clearance drop are planted inside the test
module itself (`test_the_edit_check_fails_with_the_route_at_viewer`,
`test_the_clearance_drop_check_fails_with_the_stored_selection_returned`)."""

import os
import subprocess
import tempfile

SRC = "services/api/batch_expansion.py"
TESTS = "../OspreyFlow_Build/tests/services/api/test_batch_expansion.py"
PLANTS = [
    ("expanded as no one: the requester's scope dropped",
     "    scoped = await scope_to_case(\n        principal, case_id, datasets, holds_a_level=holds_a_level_in(investigations)\n    )\n",
     '    scoped = principal.model_copy(update={"datasets": None, "clearance": "SECRET"})\n',
     "hidden_node or requesters_own_scope"),
    ("the Editor re-check at run time dropped",
     "        await investigations().get_authorized(case_id, principal, need=AccessLevel.EDITOR)\n",
     "        pass\n", "lost_edit"),
    ("past the cap, cut to fit",
     "    if len(node_ids) > MAX_NODES:\n",
     "    node_ids = node_ids[:MAX_NODES]\n    if False:\n", "past_the_cap"),
    ("past the link cap, cut to fit",
     "    if len(links) > MAX_EDGES:\n",
     "    links = links[:MAX_EDGES]\n    if False:\n", "past_the_cap"),
    ("nothing found saved as an empty view",
     "    if not node_ids:\n        return _Refused(refusal=BatchRefusal(code=\"found_nothing\"))\n", "",
     "finding_nothing"),
    ("the exception's own words served",
     "    if record.state == \"failed\" or record.result is None:\n        return BatchExpansion(id=job_id, state=\"failed\", words=FAILED_WORDS)\n",
     "    if record.state == \"failed\" or record.result is None:\n        return BatchExpansion(id=job_id, state=\"failed\", words=record.error or FAILED_WORDS)\n",
     "failed_batch_says"),
    ("another member's job read",
     "        and (payload.get(\"principal\") or {}).get(\"id\") == reader.id\n", "",
     "another_members"),
    ("one at a time not held",
     "        if record is None or (record.state in (\"pending\", \"running\") and not abandoned(record)):\n",
     "        if False:\n", "second_batch"),
    ("a view saved and not audited kept",
     "        await views.delete(case_id, view.id, principal.id)\n", "", "not_audited"),
    ("the view's input built by model_construct, every validator skipped",
     "    lens = BatchViewInput(\n",
     "    lens = BatchViewInput.model_construct(\n", "same_validators"),
    ("a job left running by a stopped worker never given up",
     "    if record.state != \"running\" or record.started_at is None:\n",
     "    if True:\n", "stopped_worker"),
    ("no time limit",
     "            outcome = await asyncio.wait_for(work, time_limit or TIME_LIMIT_SECONDS)\n",
     "            outcome = await work\n", "too_long"),
    ("the job run in the worker's own context, not a task of its own",
     "    work = asyncio.create_task(\n        _expand_and_save(payload, principal, say, graph, views, investigations, datasets, audit)\n    )\n",
     "    work = _expand_and_save(payload, principal, say, graph, views, investigations, datasets, audit)\n",
     "scope_ends"),
]
ENV = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", VALKEY_PORT="59993",
           CLICKHOUSE_HTTP_PORT="59994")
ENV.pop("OSPREY_LANE", None)


def run(k: str) -> subprocess.CompletedProcess[str]:
    env = dict(ENV, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="plant-pyc-"))
    args = [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
            "no:cacheprovider", TESTS]
    return subprocess.run(args + (["-k", k] if k else []), capture_output=True, text=True, env=env)


original = open(SRC).read()
try:
    for name, before, after, k in PLANTS:
        assert original.count(before) == 1, (name, original.count(before))
        open(SRC, "w").write(original.replace(before, after))
        r = run(k)
        tail = r.stdout.strip().splitlines()[-1]
        print(f"{'RED  ' if r.returncode else 'GREEN?!'} | {name} | -k {k!r} | {tail}")
        open(SRC, "w").write(original)
    print("CONTROL (unplanted, fresh cache):", run("").stdout.strip().splitlines()[-1])
finally:
    open(SRC, "w").write(original)
