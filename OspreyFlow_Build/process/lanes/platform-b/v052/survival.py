"""Step 6's proof that the data made on v0.5.1 is still there after the upgrade (the orchestrator's review of
v052-r1, must 2). R1's `check` makes a new case, hotlist and load each time it runs, and saves the new case's id
over the last (`r1_kind.py` `save(case=…)`), so running it after the upgrade proves the candidate works, not
that v0.5.1's data survived. This reads v0.5.1's own data instead:

    r1_live.sh survival snap      # after v0.5.1's `check` (row 2), before the backup and the upgrade
    r1_live.sh survival verify    # after the upgrade (row 4), before the candidate's `check` (row 5)

`snap` writes, from the case R1's check saved: the case's id and name, the hotlists on it, how many nodes
search finds for the load's own name (`R1Synthetic`), the Ingest claim's files, and the hotlist's alerts on the
load. Its file is kept in R1's state folder as `v052-pre-upgrade.json`, beside `state.json`, so a later
`check` cannot overwrite it. `verify` reads the same things for the same case after the upgrade and records one
PASS or FAIL line each (`records/<time>-survival.log`); any FAIL exits 1. Nothing it reads or records is a
token or a secret.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GATES = HERE.parents[1] / "platform" / "gates"
SNAP = "v052-pre-upgrade.json"
#: What R1's check loads and rules on (`r1_kind.py` checks: the load's family name, the hotlist's number).
LOAD_NAME = "R1Synthetic"
HOTLIST_NUMBER = "+447700900123"


def _r1() -> Any:
    sys.path.insert(0, str(GATES))
    import r1_kind  # platform's driver, imported, never changed here

    return r1_kind


def read(r1: Any, case: str) -> dict[str, Any]:
    """What v0.5.1's check left in its case, as the Conduit answers it now."""
    c = r1.door()
    admin = {"Authorization": f"Bearer {r1.token()}"}

    def get(path: str, **params: Any) -> Any:
        r = c.get(path, headers=admin, params=params or None)
        if r.status_code != 200:
            raise SystemExit(f"GET {path} refused: {r.status_code} {r.text[:200]}")
        return r.json()

    found = c.post(f"/v1/investigations/{case}/search", headers=admin, json={"query": LOAD_NAME, "limit": 5})
    if found.status_code != 200:
        raise SystemExit(f"search refused: {found.status_code} {found.text[:200]}")
    hotlists = get(f"/v1/investigations/{case}/hotlists")
    hotlists = hotlists if isinstance(hotlists, list) else hotlists.get("hotlists", [])
    ids = sorted(str(h.get("id")) for h in hotlists if h.get("identifier") == HOTLIST_NUMBER)
    alerts = get(f"/v1/investigations/{case}/alert-queue", status="all")
    files = get(f"/v1/investigations/{case}/ingest/source-files")
    files = files if isinstance(files, list) else files.get("files", [])
    return {
        "case": case,
        "name": get(f"/v1/investigations/{case}").get("name"),
        "hotlists": ids,
        "found": len(found.json().get("nodes") or []),
        "alerts": sorted(
            str((a.get("alert") or a).get("rule_id")) for a in alerts
            if any((a.get("alert") or a).get("rule_id") == f"hotlist:{i}" for i in ids)
        ),
        "files": sorted(f.get("name", "") for f in files),
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """One line per thing v0.5.1 made: PASS when the candidate still holds it."""
    def line(ok: bool, what: str) -> str:
        return f"{'PASS' if ok else 'FAIL'} {what}"

    return [
        line(after["name"] == before["name"], f"v0.5.1's case {before['case']} is there ({after['name']!r})"),
        line(bool(before["hotlists"]) and after["hotlists"] == before["hotlists"],
             f"its hotlist on {HOTLIST_NUMBER} is there ({after['hotlists']})"),
        line(before["found"] > 0 and after["found"] == before["found"],
             f"search finds the load's {LOAD_NAME} as before ({before['found']} then {after['found']})"),
        line(bool(before["alerts"]) and set(before["alerts"]) <= set(after["alerts"]),
             f"the hotlist's alert on the load is there ({after['alerts']})"),
        line(bool(before["files"]) and set(before["files"]) <= set(after["files"]),
             f"the Ingest claim's files are there ({after['files']})"),
    ]


def snap(r1: Any) -> dict[str, Any]:
    case = r1.state().get("case")
    if not case:
        raise SystemExit("no case in R1's state: run v0.5.1's `check` first (row 2)")
    held = read(r1, case)
    if not (held["hotlists"] and held["found"] and held["alerts"] and held["files"]):
        raise SystemExit(f"v0.5.1's check left less than it should; nothing to prove survives: {held}")
    (r1.STATE / SNAP).write_text(json.dumps(held, indent=2))
    print(f"snap: {held}")
    return held


def verify(r1: Any) -> list[str]:
    path = r1.STATE / SNAP
    if not path.is_file():
        raise SystemExit(f"no {SNAP}: run `survival snap` before the upgrade")
    before = json.loads(path.read_text())
    lines = compare(before, read(r1, before["case"]))
    r1.record("survival").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    if any(line.startswith("FAIL") for line in lines):
        raise SystemExit("v0.5.1's data did not all survive the upgrade")
    return lines


def main(argv: list[str]) -> int:
    if argv[:1] == ["snap"]:
        snap(_r1())
        return 0
    if argv[:1] == ["verify"]:
        verify(_r1())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
