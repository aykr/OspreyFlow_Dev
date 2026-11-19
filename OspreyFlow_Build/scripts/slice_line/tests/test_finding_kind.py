"""Each finding of the verifier's record says its kind: a fault in behaviour, or a gap in a test (the owner's ruling 4 of
19 November 2026, which the extra rounds' briefs asked for in words only; the owner's order of 19 November makes it a
field of the record).

The verifier runs as run_seat.py runs it, in a throwaway repository, with one thing stood in: the Claude session. The
suite never starts one, so `launch` is replaced by a stand-in that answers with the result line a `claude -p
--json-schema` session's stream ends with (its `structured_output`), and records the prompt it was given. Everything
after that (the record, the phase, the stop note) is run_seat.py's own code.
"""
from __future__ import annotations

import json

from test_gates import SRC, built, sh, stop_gate, world  # noqa: F401  (world is a fixture)

FAULT, GAP = "fault", "test_gap"


def finding(kind=None, what="x"):
    f = {"what": what, "evidence": f"evidence for {what}", "file": "feature.txt", "line": 1}
    if kind is not None:
        f["kind"] = kind
    return f


def at_verifier(w, round_=1, limit=2):
    """S1 built green (the Stop hook's test record at the tip) and waiting for the verifier."""
    wt, tip = built(w)
    assert stop_gate(w, wt) is None
    assert (w["data"] / f"records/S1/tests-{tip}.json").exists()
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(phase="verifying", tip=tip, round=round_, rounds_limit=limit)
    p.write_text(json.dumps(st))
    return wt, tip


def run_verifier(w, tip, findings, verdict="findings"):
    """run_seat.verifier('S1'), its session stood in by a result line carrying this verdict. Returns (exit, prompts)."""
    t = w["tmp"] / "verifier-transcript.jsonl"
    t.write_text(json.dumps({"type": "assistant", "text": f"{verdict} {tip}"}) + "\n")
    prompts = w["tmp"] / "prompts.json"
    code = f"""
import json, sys
sys.path.insert(0, {str(w['lines'])!r})
import run_seat
seen = []
def launch(seat, account, cwd, prompt, model, effort, env_extra, log, extra=None, interactive=False):
    seen.append(prompt)
    out = {{"verdict": {verdict!r}, "commit": {tip!r}, "findings": {json.dumps(findings)}}}
    return {{"type": "result", "subtype": "success", "session_id": "v-" + str(len(seen)), "structured_output": out,
            "usage": {{}}, "total_cost_usd": 0}}
run_seat.launch = launch
run_seat.transcript_of = lambda account, sid: {str(t)!r}
rc = run_seat.verifier("S1")
open({str(prompts)!r}, "w").write(json.dumps(seen))
sys.exit(rc)
"""
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert "Traceback" not in p.stderr, p.stderr
    return p, json.loads(prompts.read_text())


def record(w, tip):
    return json.loads((w["data"] / f"records/S1/verify-{tip}.json").read_text())


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def test_finding_kind_is_a_required_field_of_the_verdict_with_exactly_two_values(world):
    w = world
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; "
            "print(json.dumps(run_seat.VERDICT_SCHEMA))")
    schema = json.loads(sh([w["py"], "-c", code], w["repo"], w["env"]).stdout)
    item = schema["properties"]["findings"]["items"]
    assert item["properties"].get("kind") == {"enum": [FAULT, GAP]}, item
    assert "kind" in item["required"], item


def test_finding_kind_is_asked_for_in_the_verifiers_prompt_and_its_definition(world):
    w = world
    wt, tip = at_verifier(w)
    p, prompts = run_verifier(w, tip, [finding(GAP)])
    assert prompts and all(f"'{FAULT}'" in pr and f"'{GAP}'" in pr for pr in prompts), prompts
    agent = (SRC.parents[2] / ".claude/agents/slice-verifier.md").read_text()
    assert f"`{FAULT}`" in agent and f"`{GAP}`" in agent


def test_finding_kind_is_kept_in_the_record_verbatim_and_counted(world):
    w = world
    wt, tip = at_verifier(w)
    given = [finding(FAULT, "a"), finding(GAP, "b"), finding(None, "c"), finding("a nit", "d")]
    p, _ = run_verifier(w, tip, given)
    rec = record(w, tip)
    assert rec["findings"] == given                                   # verbatim: nothing added, nothing dropped
    assert rec["kinds"] == {FAULT: 1, GAP: 1, "no kind": 2}, rec.get("kinds")


def test_finding_kind_split_is_named_in_the_stop_note_at_the_rounds_limit(world):
    w = world
    wt, tip = at_verifier(w, round_=2, limit=2)
    p, _ = run_verifier(w, tip, [finding(FAULT, "a"), finding(GAP, "b"), finding(GAP, "c"), finding(None, "d")])
    st = state(w)
    assert st["phase"] == "stopped", st
    assert "1 fault in behaviour, 2 gaps in a test, 1 with no kind" in st["note"], st["note"]


def test_finding_kind_is_read_from_the_old_prefix_only_in_a_record_written_before_the_field(world):
    """GG6 and BL6's records came before the field: their findings begin "GAP IN A TEST:" or "FAULT IN BEHAVIOUR:"
    (the extra rounds' briefs). The prefix is the kind there and nowhere else; a kind field always wins."""
    w = world
    old = {"verdict": "findings", "findings": [{"what": "GAP IN A TEST: a", "evidence": "e"},
                                               {"what": "  FAULT IN BEHAVIOUR: b", "evidence": "e"},
                                               {"what": "c, unmarked", "evidence": "e"},
                                               {"what": "GAP IN A TEST: d", "evidence": "e", "kind": "a nit"}]}
    new = {**old, "kinds": {}}
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import run_seat as r; "
            f"old, new = {json.dumps(old)!r}, {json.dumps(new)!r}; old, new = json.loads(old), json.loads(new); "
            "print(json.dumps([[r.kind_of(f, r.is_legacy(x)) for f in x['findings']] for x in (old, new)]))")
    got = json.loads(sh([w["py"], "-c", code], w["repo"], w["env"]).stdout)
    assert got == [[GAP, FAULT, None, None], [None, None, None, None]], got
