"""M10's words half, shown able to fire (rule 15; the orchestrator, 14 November 2026). Inside step
4's runner (`OSPREY_MEASURE_BASE`, `_CASE`, `_CONTROLS`, `_LEAKS`): for the first 5 leak cases, the
hidden report's own title searched as its control, a reader cleared for it, so the report is in the
answer legitimately; then `measure_leaks`' own words check (`_answer_strings`, the echo left out, a
substring lower-cased) with the case's `never_text`, as if the reader were not cleared. A check
that fires shows a leaked report would be caught by its words; one that does not shows the words
never surface. Read-only: searches only, each writing its own audit row, as M10 does."""
import json, os, sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[5] / "OspreyFlow_Core")]
from scripts import measure_search as ms


def paths(value, at=""):
    if isinstance(value, str):
        yield at, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield f"{at}.{k} (key)", str(k)
            yield from paths(v, f"{at}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from paths(v, f"{at}[{i}]")


base, case = os.environ["OSPREY_MEASURE_BASE"], os.environ["OSPREY_MEASURE_CASE"]
controls = json.loads(os.environ["OSPREY_MEASURE_CONTROLS"])
cases = [json.loads(l) for l in Path(os.environ["OSPREY_MEASURE_LEAKS"]).read_text().splitlines() if l][:5]
fired = 0
for leak in cases:
    path, body = ms._leak_request(case, leak)
    _ms, answer, error = ms._send(base, path, body, controls[leak["control"]])
    print("==", leak["hidden"], "| control:", leak["control"], "| never_text:", leak["never_text"], "| error:", error)
    if answer is None:
        continue
    named = any(leak["hidden"] in s for _a, s in paths(answer))
    texts = [t.lower() for t in ms._answer_strings(answer, leak["query"])]
    hit = [w for w in leak["never_text"] if any(w.lower() in t for t in texts)]
    fired += bool(hit)
    print(f"   the hidden report in the answer: {named}; the words check fires on: {hit}")
    for at, s in paths(answer):
        if any(w.lower() in s.lower() for w in leak["never_text"]):
            print(f"   {at}: {s[:120]!r}")
    for r in answer.get("results", [])[:2]:
        print("   result:", r.get("node_ids"), r.get("date"), (r.get("match") or {}).get("band"))
print(f"positive control: the words check fired on {fired} of {len(cases)}")
