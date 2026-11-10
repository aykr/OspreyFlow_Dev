"""T1 part 1's table from the meter's records (`t1_meter.py`). Run from the repository root as
`OspreyFlow_Core/.venv/bin/python OspreyFlow_Build/process/lanes/admin/t1/t1_table.py <meter.jsonl> <stack>`.
It prints, in Markdown:
- the share of the run's test time spent in sleeps;
- the share in tests that reached no store's port (the stack's ports, from `scripts/lane_stacks.tsv`);
- the time in the files that open their own graph (`arcadedb_adapter(`);
- the 30 slowest tests, and the 25 slowest files.

`T1_P1_TABLE.md` is its output for the measured run.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[4]
_NAMES = {"arcadedb": "ArcadeDB", "postgres": "Postgres", "valkey": "Valkey", "objectstore": "object store",
          "clickhouse": "ClickHouse"}  # fmt: skip


def store_ports(stack: str) -> dict[int, str]:
    ports = {}
    for line in (BUILD / "scripts" / "lane_stacks.tsv").read_text().splitlines():
        cols = line.split("\t")
        if not line.startswith("#") and len(cols) >= 4 and cols[0] == stack and cols[3].isdigit():
            ports[int(cols[3])] = _NAMES.get(cols[1], cols[1])
    return ports


def main(meter: str, stack: str) -> None:
    ports = store_ports(stack)
    rows = [json.loads(l) for l in Path(meter).read_text().splitlines() if l.strip()]
    for r in rows:
        r["t"] = sum(r["phases"].values())
        r["stores"] = sorted({ports[p] for p in r["ports"] if p in ports})
        r["file"] = r["nodeid"].split("::")[0].replace("../OspreyFlow_Build/", "")
    tot = sum(r["t"] for r in rows)
    slept = sum(min(r["sleep_s"], r["t"]) for r in rows)
    nostore = [r for r in rows if not r["stores"]]
    ns_t = sum(r["t"] for r in nostore)
    uses = {f for f in {r["file"] for r in rows} if (BUILD / f).exists() and "arcadedb_adapter(" in (BUILD / f).read_text()}
    ad = [r for r in rows if r["file"] in uses and "ArcadeDB" in r["stores"]]
    ad_t = sum(r["t"] for r in ad)
    print(f"{len(rows)} tests, {tot / 3600:.2f} h of test time (the run's wall: 12,115 s by pytest, 3 h 22 min).\n")
    print(f"- **Sleeps and polling:** {slept / 60:.1f} min, {100 * slept / tot:.1f}% of test time (time inside "
          "`time.sleep` and `asyncio.sleep`; an upper bound, since concurrent sleeps are each counted).")  # fmt: skip
    print(f"- **Tests that reached no store:** {len(nostore)} of {len(rows)} ({100 * len(nostore) / len(rows):.0f}%), "
          f"{ns_t / 60:.1f} min ({100 * ns_t / tot:.1f}% of test time).")  # fmt: skip
    print(f"- **Tests in files that open `arcadedb_adapter` and reached ArcadeDB:** {len(ad)}, {ad_t / 3600:.2f} h "
          f"({100 * ad_t / tot:.0f}% of test time). Each such open applied the schema one statement at a time, about "
          "16 s on a fresh database (the batched schema's live proof), now 0.3 s.")  # fmt: skip
    print("\n**The 30 slowest tests**\n\n| # | Test | s | in sleeps, s | stores reached |\n| --- | --- | --- | --- | --- |")
    for i, r in enumerate(sorted(rows, key=lambda r: -r["t"])[:30], 1):
        name = r["nodeid"].replace("../OspreyFlow_Build/", "")
        print(f"| {i} | `{name}` | {r['t']:.1f} | {r['sleep_s']:.1f} | {', '.join(r['stores']) or 'none'} |")
    files: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        files[r["file"]].append(r)
    print("\n**By file, the 25 slowest**\n\n| File | tests | min | in sleeps, s | tests reaching no store |\n"
          "| --- | --- | --- | --- | --- |")  # fmt: skip
    for f, rs in sorted(files.items(), key=lambda kv: -sum(r["t"] for r in kv[1]))[:25]:
        print(f"| `{f}` | {len(rs)} | {sum(r['t'] for r in rs) / 60:.1f} | {sum(r['sleep_s'] for r in rs):.0f} | "
              f"{sum(1 for r in rs if not r['stores'])} |")  # fmt: skip


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
