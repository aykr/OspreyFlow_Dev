"""Where a leak case's hidden words sit in m10-part's answer (M10's second turn on stack d, 14
November 2026: 500 of 500 leak cases failed on the hidden document's title, no hidden id). Inside
step 4's runner (`OSPREY_MEASURE_BASE`, `_CASE`, `_PART_TOKEN`): sends m10-part's search for the
first few leak cases, as `measure_leaks` does, and prints each string's path that holds the words.
Read-only: searches only, each writing its own audit row, as M10 does."""
import json, os, sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[5] / "OspreyFlow_Core")]
from scripts import measure_search as ms

def paths(value, at=""):
    if isinstance(value, str):
        yield at, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from paths(v, f"{at}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from paths(v, f"{at}[{i}]")

base, case, token = (os.environ[k] for k in ("OSPREY_MEASURE_BASE", "OSPREY_MEASURE_CASE", "OSPREY_MEASURE_PART_TOKEN"))
cases = [json.loads(l) for l in Path(os.environ["OSPREY_MEASURE_LEAKS"]).read_text().splitlines() if l][:4]
for leak in cases:
    path, body = ms._leak_request(case, leak)
    _ms, answer, error = ms._send(base, path, body, token)
    print("==", leak["name"][:90], "| sent:", body.get("query"), "| error:", error)
    if answer is None:
        continue
    print("   top-level keys:", sorted(answer), "| source:", answer.get("source"), "| total:", answer.get("total"))
    words = [w.lower() for w in leak.get("never_text", [])]
    for at, s in paths(answer):
        if any(w in s.lower() for w in words) or any(i in s for i in leak["never_ids"]):
            print(f"   {at}: {s[:160]!r}")
    for r in answer.get("results", [])[:3]:
        print("   result:", r.get("node_ids"), r.get("type"), r.get("title"), (r.get("match") or {}).get("band"), (r.get("match") or {}).get("why"))
