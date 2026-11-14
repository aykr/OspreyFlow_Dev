"""rules-b am20's plants (rule 15, ADR-124 Amendment 20): each protection of the record-id
`edges_among` removed at its real site in the graph adapter, and the tests that name it run with a
fresh bytecode cache; then the files restored and the module run as a control.

Offline (the default): `test_edges_among_from_record_ids.py`, with the closed ports. Live (`--live`,
under a lease, through `stack_lease.sh remote`): `test_edges_among_at_scale.py`, for what only a store
shows (the access step on the far end, the far end's test against a real answer). Run from
OspreyFlow_Core. The query as built is shown red separately (`red-first.txt`)."""

import os
import subprocess
import sys
import tempfile

ADAPTER = "packages/adapters/graph_arcadedb/adapter.py"
BUILDERS = "packages/adapters/graph_arcadedb/builders.py"
OFFLINE = "../OspreyFlow_Build/tests/adapters/graph_arcadedb/test_edges_among_from_record_ids.py"
LIVE = "../OspreyFlow_Build/tests/conformance/graph_port/test_edges_among_at_scale.py"

OFFLINE_PLANTS = [
    ("the far end not tested", ADAPTER,
     '                if row["t"] in wanted\n', "", "far_end"),
    ("a chunk where nothing resolved not sent", ADAPTER,
     "            query = render_edges_among_gremlin(rids, self._access, principal, edge_types)\n",
     "            if not rids:\n                continue\n"
     "            query = render_edges_among_gremlin(rids, self._access, principal, edge_types)\n",
     "absent_id"),
    ("every id in one query, no chunks", ADAPTER,
     "        for chunk in _id_chunks(sorted(wanted)):\n",
     "        for chunk in [sorted(wanted)]:\n", "grows_with_its_chunk"),
    ("the link types not passed", ADAPTER,
     "            query = render_edges_among_gremlin(rids, self._access, principal, edge_types)\n",
     "            query = render_edges_among_gremlin(rids, self._access, principal, None)\n",
     "link_types"),
    ("the start looked up by scanning the store", BUILDERS,
     '        else f"g.V({groovy_string_list_literal(list(record_ids))})"\n',
     '        else f\'g.V().has("id",within({groovy_string_list_literal(list(record_ids))}))\'\n',
     "scanning"),
    ("a one-node set queried", ADAPTER,
     "        if len(wanted) < 2:\n", "        if not wanted:\n", "one_node"),
]
LIVE_PLANTS = [
    ("the far end's access step dropped", BUILDERS,
     "        f\".inV().{has_access}.as('t')\"\n", "        \".inV().as('t')\"\n", "secret_far_end"),
    ("the far end not tested", ADAPTER,
     '                if row["t"] in wanted\n', "", "chunk_boundary"),
]
ENV = dict(os.environ)
LIVE_RUN = "--live" in sys.argv
if not LIVE_RUN:
    ENV.update(ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", VALKEY_PORT="59993",
               CLICKHOUSE_HTTP_PORT="59994")
    ENV.pop("OSPREY_LANE", None)
TESTS, PLANTS = (LIVE, LIVE_PLANTS) if LIVE_RUN else (OFFLINE, OFFLINE_PLANTS)


def run(k: str) -> subprocess.CompletedProcess[str]:
    env = dict(ENV, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="plant-pyc-"))
    args = [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
            "no:cacheprovider", TESTS]
    return subprocess.run(args + (["-k", k] if k else []), capture_output=True, text=True, env=env)


originals = {path: open(path).read() for path in (ADAPTER, BUILDERS)}
try:
    for name, path, before, after, k in PLANTS:
        assert originals[path].count(before) == 1, (name, originals[path].count(before))
        open(path, "w").write(originals[path].replace(before, after))
        r = run(k)
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
        print(f"{'RED  ' if r.returncode else 'GREEN?!'} | {name} | -k {k!r} | {tail}", flush=True)
        open(path, "w").write(originals[path])
    print("CONTROL (unplanted, fresh cache):", run("").stdout.strip().splitlines()[-1], flush=True)
finally:
    for path, text in originals.items():
        open(path, "w").write(text)
