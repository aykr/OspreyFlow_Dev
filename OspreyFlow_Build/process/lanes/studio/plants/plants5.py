"""L1.2c's plants (ADR-110 Amendment 16): each (file, [(old, new)], tests), run, first failure
printed, restored by md5. O1–O5 need no stack (the closed ports are pinned); L0–L3 need the stack lease."""
import hashlib, os, re, subprocess, sys, time
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parents[5]
CORE = str(ROOT / "OspreyFlow_Core")
BUILD = str(ROOT / "OspreyFlow_Build")
REVERT = f"{CORE}/services/ingest/load_revert.py"
PUB = f"{CORE}/services/api/studio_publish.py"
SCHEMA = f"{CORE}/packages/schemas/ingest.py"
UNIT = "tests/ingest/test_snapshot_withdrawal.py"
TOLD = "tests/services/api/test_link_prior_state_never_told.py"
PLANTS = {
    "O1": ("the revert counts a returning row's own merge as any merge", REVERT, [
        ("    own = {m.edge_id for m in record.own_key_merges}\n", "    own: set[str] = set()\n"),
    ], [UNIT]),
    "O2": ("the revert's written-since check removed", REVERT, [
        ("        if since:\n            refusals.append(Refusal(record.load_id, \"own_link_written_since\", since))\n",
         "        if since and False:\n            refusals.append(Refusal(record.load_id, \"own_link_written_since\", since))\n"),
    ], [UNIT]),
    "O3": ("nothing captured: the load keeps no prior state", PUB, [
        ("                report.own_key_merges = _own_key_merges(report, own_links.own, own_links.priors)\n",
         "                report.own_key_merges = []\n"),
    ], [UNIT]),
    "O4": ("every merge counted as the row's own at the revert", REVERT, [
        ("    own = {m.edge_id for m in record.own_key_merges}\n", "    own = set(record.merged_edge_ids)\n"),
    ], [UNIT]),
    "O5": ("LoadReport's prior state left in its dumps", SCHEMA, [
        ("    own_key_merges: SkipJsonSchema[list[LinkPriorState]] = Field(default_factory=list, exclude=True)\n",
         "    own_key_merges: list[LinkPriorState] = Field(default_factory=list)\n"),
    ], [TOLD]),
}
ADAPTER = f"{CORE}/packages/adapters/graph_arcadedb/adapter.py"
CONF = "tests/conformance/graph_port/test_suite.py"
LIVE = "tests/services/api/test_source_refresh_snapshot_live.py"
LIVE_PLANTS = {
    "L0": ("the adapter without the two methods (the conformance cases before it)", ADAPTER, [
        ("    async def read_link_state(\n", "    async def _absent_read_link_state(\n"),
        ("    async def restore_link_state(self,", "    async def _absent_restore_link_state(self,"),
    ], [CONF, "-k", "link_state or restored_link"]),
    "L1": ("the restore without its written-since check", ADAPTER, [
        ("        if not rows or AuditStub.model_validate(rows[0][\"audit\"]).load_id != written_by:\n",
         "        if not rows:\n"),
    ], [CONF, "-k", "link_state or restored_link"]),
    "L2": ("the restore writing the link at a weaker marking", ADAPTER, [
        ("        marking = state.handling\n",
         "        marking = state.handling.model_copy(update={\"classification\": \"OFFICIAL\"})\n"),
    ], [CONF, "-k", "link_state or restored_link"]),
    "L4": ("the restore altering one stored property (occurrences + 1)", ADAPTER, [
        ('        props = {k: v for k, v in state.stored.items() if k != "id"}\n',
         '        props = {k: v for k, v in state.stored.items() if k != "id"}\n'
         '        props["occurrences"] = int(props.get("occurrences") or 1) + 1\n'),
    ], [CONF, "-k", "round_trips_exactly"]),
    "L3": ("nothing captured, live: the load keeps no prior state", PUB, [
        ("                report.own_key_merges = _own_key_merges(report, own_links.own, own_links.priors)\n",
         "                report.own_key_merges = []\n"),
    ], [LIVE, "-k", "returning"]),
}
env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"}
if any(a in LIVE_PLANTS for a in sys.argv[1:]):
    # Live plants: only under the stack lease, the lane and leased ports set by hand.
    assert os.environ.get("OSPREY_LANE") and os.environ.get("POSTGRES_PORT") == "55433", "take the lease"
    env = dict(os.environ)
else:
    env.update({"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993",
                "CLICKHOUSE_HTTP_PORT": "59994"})
PLANTS.update(LIVE_PLANTS)
for letter in sys.argv[1:]:
    name, path, pairs, tests = PLANTS[letter]
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
