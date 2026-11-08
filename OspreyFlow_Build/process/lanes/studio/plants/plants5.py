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
        ("                merged = _own_key_merges(report, own_links.own, own_links.priors)\n",
         "                merged = []\n"),
    ], [UNIT]),
    "O4": ("every merge counted as the row's own at the revert", REVERT, [
        ("    own = {m.edge_id for m in record.own_key_merges}\n", "    own = set(record.merged_edge_ids)\n"),
    ], [UNIT]),
    "O5": ("LoadReport's prior state left in its dumps", SCHEMA, [
        ("    own_key_merges: SkipJsonSchema[list[LinkPriorState]] = Field(default_factory=list, exclude=True)\n",
         "    own_key_merges: list[LinkPriorState] = Field(default_factory=list)\n"),
    ], [TOLD]),
    "O6": ("the revert's planning comparing only the last load, not the whole record (the old shape)", REVERT, [
        ("            held = stored_digest(now_held.stored) if now_held is not None else None\n",
         "            held = (prior.left_digest if now_held is not None and now_held.load_id == record.load_id\n"
         "                    else (stored_digest(now_held.stored) if now_held is not None else None))\n"),
    ], [UNIT]),
    "O7": ("the stamping wrapper's restore without its composite guard", f"{CORE}/services/api/dataset_scope.py", [
        ("        await self._refuse_loading_here()\n        restored = await self._inner.restore_link_state(state, tx)\n",
         "        restored = await self._inner.restore_link_state(state, tx)\n"),
    ], ["tests/services/api/test_restore_link_state_through_the_wrapper.py"]),
    "O8": ("the wrapper's declared restore removed (left to __getattr__)", f"{CORE}/services/api/dataset_scope.py", [
        ("    async def restore_link_state(self, state: LinkPriorState, tx: TxId) -> bool:\n",
         "    async def _absent_restore_link_state(self, state: LinkPriorState, tx: TxId) -> bool:\n"),
        ('        if name == "restore_link_state":  # a write: declared above, with its guard, or absent\n            raise AttributeError(name)\n', ""),
    ], ["tests/services/api/test_restore_link_state_through_the_wrapper.py"]),
    "O9": ("the put-back links left out of the working sets", REVERT, [
        ("            reverting_nodes, [*record.created_edge_ids, *put_back]\n        )\n",
         "            reverting_nodes, list(record.created_edge_ids)\n        )\n"),
        ("            reverting_nodes, [*record.created_edge_ids, *put_back], final_pass=True\n",
         "            reverting_nodes, list(record.created_edge_ids), final_pass=True\n"),
    ], [UNIT]),
    "O10": ("nobody told the put-back links changed", REVERT, [
        ("        if put_back and deps.links_changed is not None:\n", "        if False:\n"),
    ], [UNIT]),
    "D4": ("L1.2d: the load not catching an ambiguous own link id", PUB, [
        ("            except AmbiguousLinkId:\n                # ADR-110 Amendment 18: two types hold the id, so which to put back is not\n",
         "            except KeyError:\n                # ADR-110 Amendment 18: two types hold the id, so which to put back is not\n"),
    ], [UNIT, "-k", "not_captured_and_its_load_stays_refused"]),
    "D5": ("L1.2d: the revert not catching an ambiguous own link id", REVERT, [
        ("            except AmbiguousLinkId:\n                ambiguous += 1\n",
         "            except KeyError:\n                ambiguous += 1\n"),
    ], [UNIT, "-k", "ambiguous"]),
}
ADAPTER = f"{CORE}/packages/adapters/graph_arcadedb/adapter.py"
CONF = "tests/conformance/graph_port/test_suite.py"
LIVE = "tests/services/api/test_source_refresh_snapshot_live.py"
LIVE_PLANTS = {
    "L0": ("the adapter without the two methods (the conformance cases before it)", ADAPTER, [
        ("    async def read_link_state(\n", "    async def _absent_read_link_state(\n"),
        ("    async def restore_link_state(self, state: LinkPriorState, tx: TxId) -> bool:\n        type_name", "    async def _absent_restore_link_state(self, state: LinkPriorState, tx: TxId) -> bool:\n        type_name"),
    ], [CONF, "-k", "link_state or restored_link"]),
    "L1": ("the restore without its whole-record check (written since, by anyone)", ADAPTER, [
        ("        if held != state.left_digest:\n            return False  # written since, by anyone\n", ""),
    ], [CONF, "-k", "link_state or restored_link or digest or its_own_type or marking_before"]),
    "L2": ("the restore writing the link at a weaker marking", ADAPTER, [
        ("        marking = state.handling\n",
         "        marking = state.handling.model_copy(update={\"classification\": \"OFFICIAL\"})\n"),
    ], [CONF, "-k", "link_state or restored_link"]),
    "L5": ("the restore's write untyped (every type holding the id)", ADAPTER, [
        ('            f"g.E().hasLabel({groovy_string_literal(state.edge_type)})"\n            f\'.has("id",{groovy_string_literal(state.edge_id)}){steps}\',\n',
         '            f\'g.E().has("id",{groovy_string_literal(state.edge_id)}){steps}\',\n'),
    ], [CONF, "-k", "its_own_type"]),
    "W1": ("withdrawn_row_links without the case", f"{CORE}/services/api/recipe_runs.py", [
        ('"SELECT row_key, edge_ids FROM withdrawn_row_keys WHERE recipe_id = $1 "\n                    "AND investigation_id = $2 AND row_key = ANY($3::text[])",\n',
         '"SELECT row_key, edge_ids FROM withdrawn_row_keys WHERE recipe_id = $1 "\n                    "AND $2::text IS NOT NULL AND row_key = ANY($3::text[])",\n'),
    ], ["tests/services/api/test_row_key_withdrawal_ledger.py::test_withdrawn_row_links_answers_this_recipe_and_case_alone"]),
    "W2": ("withdrawn_row_links without the recipe", f"{CORE}/services/api/recipe_runs.py", [
        ('"SELECT row_key, edge_ids FROM withdrawn_row_keys WHERE recipe_id = $1 "\n',
         '"SELECT row_key, edge_ids FROM withdrawn_row_keys WHERE $1::text IS NOT NULL "\n'),
    ], ["tests/services/api/test_row_key_withdrawal_ledger.py::test_withdrawn_row_links_answers_this_recipe_and_case_alone"]),
    "T0": ("for item 8's cost: the capture turned off (the sink asked directly, nothing kept)", PUB, [
        ("                own_links = _OwnLinks(sink, graph, tx) if sink is not None else None\n",
         "                own_links = None\n"),
        ("                    row_keys=own_links,\n", "                    row_keys=sink,\n"),
    ], ["tests/services/api/test_pin_calls_refresh_live.py"]),
    "D1": ("L1.2d: the merge's write untyped", ADAPTER, [
        ('                    f"g.E().hasLabel({groovy_string_literal(type_name)})"\n                    f\'.has("id",{edge_lit}){property_steps}\'\n',
         '                    f\'g.E().has("id",{edge_lit}){property_steps}\'\n'),
    ], [CONF, "-k", "merge_writes_its_own_type"]),
    "D2": ("L1.2d: read_link_state taking the first type found", ADAPTER, [
        ("        if len(held) > 1:\n            raise AmbiguousLinkId(edge_id, [t for t, _ in held])\n        ((type_name, row),) = held\n",
         "        (type_name, row) = held[0]\n"),
    ], [CONF, "-k", "refuses_an_id_two_types_hold"]),
    "D3": ("L1.2d: supersede_edge taking the first type and marking by id alone", ADAPTER, [
        ("        if len(holding) > 1:\n            raise AmbiguousLinkId(edge_id, [t for t, _ in holding])\n", ""),
        ('            f\'g.E().hasLabel({old_label}).has("id",{edge_lit})\'\n            f\'.property("superseded_by", {new_id_lit})\',\n',
         '            f\'g.E().has("id",{edge_lit}).property("superseded_by", {new_id_lit})\',\n'),
    ], [CONF, "-k", "correction_marks_only_its_own"]),
    "L4": ("the restore altering one stored property (occurrences + 1)", ADAPTER, [
        ('        props = {k: v for k, v in state.stored.items() if k != "id"}\n',
         '        props = {k: v for k, v in state.stored.items() if k != "id"}\n'
         '        props["occurrences"] = int(props.get("occurrences") or 1) + 1\n'),
    ], [CONF, "-k", "round_trips_exactly or merged_link_back_exactly"]),
    "L3": ("nothing captured, live: the load keeps no prior state", PUB, [
        ("                merged = _own_key_merges(report, own_links.own, own_links.priors)\n",
         "                merged = []\n"),
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
