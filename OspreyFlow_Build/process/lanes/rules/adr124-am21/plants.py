"""Red first (rule 15) for ADR-124 Amendment 21, `search_nodes` from its candidates. Two parts, both
offline (closed ports), each planted file restored from its own saved text, never by git:

1. red first: the new cases against main's `adapter.py` and `builders.py` (`--main <rev>`, read with
   `git show`, written over the files, restored after);
2. plants: each check planted out alone at its call site, its test red, restored, the file green.

Run from the repository root:

    PYTHONPYCACHEPREFIX=$(mktemp -d) OspreyFlow_Core/.venv/bin/python \\
        OspreyFlow_Build/process/lanes/rules/adr124-am21/plants.py --main <main's commit>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
ADAPTER = CORE / "packages/adapters/graph_arcadedb/adapter.py"
BUILDERS = CORE / "packages/adapters/graph_arcadedb/builders.py"
TESTS = "../OspreyFlow_Build/tests/adapters/graph_arcadedb/test_search_nodes_from_candidates.py"

#: (name, file, the text planted out, what replaces it, the test that must go red)
PLANTS = [
    (
        "A1 a search starts from every vertex again",
        BUILDERS,
        '            f"g.V({groovy_string_list_literal(list(self.record_ids))})"\n'
        "            if self.record_ids\n",
        '            "g.V()"\n            if self.record_ids\n',
        "test_no_search_starts_from_every_vertex",
    ),
    (
        "A2 the access step dropped from the traversal",
        BUILDERS,
        'return f"{source}.{matched}.{has_access}.dedup().limit({self.limit}).elementMap()"',
        'return f"{source}.{matched}.dedup().limit({self.limit}).elementMap()"',
        "test_the_match_and_the_access_step_are_in_the_traversal_from_the_candidates",
    ),
    (
        "A3 a field asked only where it is searchable on that type (an Account not found by its name)",
        ADAPTER,
        "asked & ({p.name for p in entity.properties} | set(entity.identifiers))",
        "asked & ({p.name for p in entity.properties if p.indexed} | set(entity.identifiers))",
        "test_a_field_is_asked_of_every_type_that_holds_it_and_the_value_is_bound",
    ),
    (
        "A4 a request reader's lookups keep the gazetteer-only identifiers",
        ADAPTER,
        "            asked -= set(GAZETTEER_ONLY_IDENTIFIERS)\n",
        "            asked -= set()\n",
        "test_a_request_reader_looks_up_no_gazetteer_only_identifier",
    ),
    (
        "A5 a type the store does not hold asked",
        ADAPTER,
        "            if physical_type_name(entity.name) in stored\n",
        "            if True\n",
        "test_a_type_the_store_does_not_hold_is_not_asked",
    ),
    (
        "A6 a value nobody holds sends no query",
        ADAPTER,
        "        for chunk in _id_chunks(rids) or [[]]:\n",
        "        for chunk in _id_chunks(rids):\n",
        "test_a_value_nobody_holds_still_sends_its_query",
    ),
    (
        "A7 only the first chunk's candidates traversed",
        ADAPTER,
        "        for chunk in _id_chunks(rids) or [[]]:\n",
        "        for chunk in _id_chunks(rids)[:1] or [[]]:\n",
        "test_candidates_past_a_chunk_are_all_sent_and_the_answer_cut_at_the_limit",
    ),
    (
        "A8 the chunks' answers not cut at the limit",
        ADAPTER,
        "for r in list(found.values())[:limit]]",
        "for r in list(found.values())]",
        "test_candidates_past_a_chunk_are_all_sent_and_the_answer_cut_at_the_limit",
    ),
]


def pytest(*select: str) -> tuple[bool, str]:
    args = [
        ".venv/bin/pytest",
        "-c",
        "../OspreyFlow_Build/pytest.ini",
        "-p",
        "no:cacheprovider",
        "-q",
    ]
    run = subprocess.run(
        [*args, *(f"{TESTS}::{s}" for s in select)] if select else [*args, TESTS],
        cwd=CORE, capture_output=True, text=True,
    )  # fmt: skip
    lines = run.stdout.strip().splitlines()
    failed = [x.split("::")[-1] for x in lines if x.startswith("FAILED")]
    return run.returncode == 0, " | ".join([*failed, lines[-1] if lines else run.stderr[-300:]])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", required=True, help="main's commit, for red first")
    args = parser.parse_args()
    saved = {p: p.read_text(encoding="utf-8") for p in (ADAPTER, BUILDERS)}
    bad = 0
    try:
        ok, summary = pytest()
        print(f"built: {'GREEN' if ok else 'RED'} - {summary}")
        if not ok:
            return 1
        for path in (ADAPTER, BUILDERS):
            rel = path.relative_to(ROOT).as_posix()
            path.write_text(
                subprocess.run(["git", "show", f"{args.main}:{rel}"], cwd=ROOT, check=True,
                               capture_output=True, text=True).stdout,
                encoding="utf-8",
            )  # fmt: skip
        ok, summary = pytest()
        print(
            f"red first, main {args.main}'s adapter and builders: {'GREEN (sees nothing)' if ok else 'RED'} - {summary}"
        )
        bad += ok
        for path, text in saved.items():
            path.write_text(text, encoding="utf-8")
        for name, path, old, new, test in PLANTS:
            text = saved[path]
            if text.count(old) != 1:
                print(f"{name}: NOT PLANTED - the text is not in the file once")
                bad += 1
                continue
            path.write_text(text.replace(old, new), encoding="utf-8")
            ok, summary = pytest(test)
            print(f"{name}: {'GREEN (a plant its test does not see)' if ok else 'RED'} - {summary}")
            bad += ok
            path.write_text(text, encoding="utf-8")
    finally:
        for path, text in saved.items():
            path.write_text(text, encoding="utf-8")
    ok, summary = pytest()
    print(f"restored: {'GREEN' if ok else 'RED'} - {summary}")
    return 1 if bad or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
