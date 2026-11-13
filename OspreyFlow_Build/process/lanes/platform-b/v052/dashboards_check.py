"""v052-r1's dashboards check (ADR-148 Amendments 9 to 11): Superset and the report sync on the kind cluster
R1 installed, signed in through the Entra stand-in. Its own step beside case-b's `spec08_poc.py`, run after
the install and before case-b's `install_verify`, which then finds Superset's and the report sync's
sign-ins, their workloads and Superset's database exercised.

What it shows, each line PASS or FAIL, stopping at the first that fails (R1's way, `r1_kind.checks`):

1. **People.** Three of the stand-in tenant's people beside the first administrator (the stand-in's
   `users`, picked by `login_hint`), added in Admin › People by object id and given roles there: a Reports
   Viewer; a builder (`right:manage_dashboards` with `reports_viewer`); and one with no role.
2. **A dashboard identity and the report sync.** The report sync's registration (`r1_kind_entra.yaml`)
   registered in Admin › Dashboards by its application id as the board `r1-board`, given Viewer on a case
   by its Author; its secret given to our Secret's `REPORT_SYNC_DASHBOARDS` as the Terraform's variable
   would, the report sync restarted, and its first pull seen in Admin › Dashboards.
3. **Superset's sign-in** (Amendment 9), through Superset's own `/login/entra` and the stand-in's
   `/authorize`, each person's role read from Superset: the administrator Admin, the builder Alpha, the
   Reports Viewer Gamma, the person with no role refused; and a role re-read at the next sign-in.
4. **Building** (the owner's Q2): the administrator saves the board `r1-board`; the builder saves a
   dashboard (201); the Reports Viewer is refused (403).
5. **Embedding** (Amendment 11 point 8): through the Glass's door, the Reports Viewer is offered
   `r1-board` and given a guest token, which opens the board in Superset (and nothing opens without it);
   a person with no reports right is refused (403); one whose clearance is below the identity's is
   offered nothing and refused the token (404).

    python3 dashboards_check.py run       # on the run's host, after R1's install, kubectl at the cluster
    python3 dashboards_check.py plan      # the steps, offline

Needs, in the run's `osprey.yaml` (r1_kind_osprey.yaml): `reporting: {sync: true, superset: true}` and
`cloud_platform.claims.superset_client_id` the stand-in's Superset registration; refused in words without.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GATES = HERE.parents[1] / "platform" / "gates"
POD_SCRIPT = HERE / "superset_pod.py"
BOARD = "r1-board"
#: The stand-in tenant's people (platform's `users`, by `preferred_username`), beside its first administrator.
PEOPLE = {
    "admin@r1.test": None,  # users[0], the first administrator, whose oid is the claims'
    "reader@r1.test": "50000000-0000-4000-8000-0000000000b1",
    "builder@r1.test": "50000000-0000-4000-8000-0000000000b2",
    "nobody@r1.test": "50000000-0000-4000-8000-0000000000b3",
}
ROLES = {
    "reader@r1.test": ["reports_viewer"],
    "builder@r1.test": ["reports_viewer", "right:manage_dashboards"],
    "nobody@r1.test": [],
}
#: What Superset gives each (Amendment 9 point 3; Q2), and what building answers.
SUPERSET_ROLE = {"admin@r1.test": ["Admin"], "builder@r1.test": ["Alpha"], "reader@r1.test": ["Gamma"]}

PLAN = [
    "people: three added by object id and given their roles",
    "a case, with Viewer for the Reports Viewer and the dashboard identity",
    "the dashboard identity r1-board registered by the report sync's application id",
    "the report sync given its secret, restarted, and its first pull seen",
    "Superset: the administrator signs in as Admin and saves the board r1-board",
    "Superset: the builder signs in as Alpha and saves a dashboard",
    "Superset: the Reports Viewer signs in as Gamma and is refused saving one",
    "Superset: the person with no role is refused at sign-in",
    "Superset: a role is re-read at the next sign-in (the builder made a Reports Viewer: Gamma)",
    "embedding: the Reports Viewer is offered r1-board and its guest token opens it, nothing without",
    "embedding: no reports right is refused (403); a lower clearance is offered nothing (404)",
]


def _r1() -> Any:
    sys.path.insert(0, str(GATES))
    import r1_kind  # platform's driver, imported, never changed here

    return r1_kind


def pod(r1: Any, *args: str) -> dict[str, Any]:
    """`superset_pod.py` in the api pod, its one JSON line back."""
    out = r1.kubectl("exec", "-i", "deploy/api", "--", "/app/.venv/bin/python", "-I", "-", r1.GLASS, *args,
                     stdin=POD_SCRIPT.read_text())  # fmt: skip
    return json.loads(out.strip().splitlines()[-1])


def run() -> None:
    import yaml

    r1 = _r1()
    log = r1.record("dashboards")
    lines: list[str] = []

    def ok(what: str, cond: bool, said: Any = "") -> None:
        line = f"{'PASS' if cond else 'FAIL'} {what}" + (f": {str(said)[:300]}" if said != "" else "")
        print(line)
        lines.append(line)
        log.write_text("\n".join(lines) + "\n")
        if not cond:
            raise SystemExit(f"check failed: {what} (record {log})")

    config = yaml.safe_load(r1.CONFIG.read_text())
    claims = config["cloud_platform"]["claims"]
    reporting = config.get("reporting") or {}
    ok("the run's osprey.yaml switches Superset and the report sync on",
       reporting.get("superset") is True and reporting.get("sync") is True, reporting)
    entra = yaml.safe_load((GATES / "r1_kind_entra.yaml").read_text())
    ok("and names the stand-in's Superset registration",
       claims.get("superset_client_id") == entra["superset"]["client_id"], claims.get("superset_client_id"))
    admin_oid = claims["first_administrators"][0]
    people = {hint: oid or admin_oid for hint, oid in PEOPLE.items()}
    clearance_claim = claims["clearance"]["claim"]

    def token(hint: str, **overrides: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {r1.token(oid=people[hint], preferred_username=hint, **overrides)}"}

    c = r1.door()
    admin = token("admin@r1.test")

    # 1. People.
    for hint, roles in ROLES.items():
        r = c.post("/v1/admin/people/by-object-id", headers=admin, json={"object_id": people[hint]})
        ok(f"{hint} is added in Admin › People", r.status_code in (201, 409), f"{r.status_code} {r.text[:160]}")
        r = c.put(f"/v1/admin/people/{people[hint]}/roles", headers=admin, json={"roles": roles})
        ok(f"{hint} is given {roles or 'no role'}", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    me = c.get("/v1/me", headers=token("reader@r1.test")).json()

    # 2. A case, the dashboard identity, the report sync.
    r = c.post("/v1/investigations", headers=admin, json={"name": "R1 reports case", "new_dataset_name": f"R1 reports {int(time.time())}"})
    ok("a case is made for the board", r.status_code == 201, r.text[:200])
    case = r.json()["id"]
    app_id = entra["report-sync"]["client_id"]
    r = c.post("/v1/admin/dashboards", headers=admin,
               json={"name": BOARD, "clearance": me["clearance"], "org_unit": me["org_unit"], "application_id": app_id})  # fmt: skip
    ok(f"the dashboard identity {BOARD} is registered by its application id", r.status_code in (201, 409), f"{r.status_code} {r.text[:200]}")
    for who in (people["reader@r1.test"], app_id):
        r = c.put(f"/v1/investigations/{case}/access/grants/{who}", headers=admin, json={"level": "viewer"})
        ok(f"the case's Author gives {who} Viewer", r.status_code == 204, f"{r.status_code} {r.text[:200]}")
    secret = r1.entra_clients()["report-sync"]
    given = json.dumps([{"client_id": app_id, "secret": secret, "weeks": 4}])
    r1.kubectl("patch", "secret", "ospreyflow-secrets", "--type", "merge",
               "-p", json.dumps({"stringData": {"REPORT_SYNC_DASHBOARDS": given}}))  # fmt: skip
    r1.kubectl("rollout", "restart", "deploy/report-sync")
    r1.kubectl("rollout", "status", "deploy/report-sync", "--timeout=10m")
    pulled = None
    for _ in range(60):
        listed = c.get("/v1/admin/dashboards", headers=admin).json()
        pulled = next((d for d in listed if d.get("client_id") == app_id), None)
        if pulled and pulled.get("last_pulled"):
            break
        time.sleep(10)
    ok("the report sync signs in with its app-only token and pulls the case (Admin › Dashboards)",
       bool(pulled and pulled.get("last_pulled") and not pulled.get("last_failure")), pulled)

    # 3 and 4. Superset's sign-in, its roles, building.
    for hint in ("admin@r1.test", "builder@r1.test", "reader@r1.test"):
        s = pod(r1, "signin", hint)
        ok(f"{hint} signs in to Superset as {SUPERSET_ROLE[hint][0]}",
           s.get("signed_in") is True and s.get("roles") == SUPERSET_ROLE[hint], s)
        ok(f"{hint}'s Superset account is the Conduit's principal", s.get("username") == people[hint], s)
    s = pod(r1, "build", "admin@r1.test", "R1 board", BOARD)
    ok(f"the administrator saves the board {BOARD}", s.get("status") == 201, s)
    board_id = s.get("id")
    s = pod(r1, "build", "builder@r1.test", "R1 builder's own board")
    ok("the builder saves a dashboard", s.get("status") == 201, s)
    s = pod(r1, "build", "reader@r1.test", "R1 refused board")
    ok("the Reports Viewer is refused saving one", s.get("status") == 403, s)
    s = pod(r1, "signin", "nobody@r1.test")
    ok("the person with no reports right is refused at Superset's sign-in", s.get("signed_in") is False, s)
    r = c.put(f"/v1/admin/people/{people['builder@r1.test']}/roles", headers=admin, json={"roles": ["reports_viewer"]})
    s = pod(r1, "signin", "builder@r1.test")
    ok("a role is re-read at the next sign-in (the builder, now a Reports Viewer, is Gamma)",
       r.status_code == 200 and s.get("roles") == ["Gamma"], s)

    # 5. Embedding, through the Glass's door.
    reader = token("reader@r1.test")
    r = c.get("/v1/reports/dashboards", headers=reader)
    ok(f"the Reports Viewer is offered {BOARD}", r.status_code == 200 and any(d.get("slug") == BOARD for d in r.json()), r.text[:200])
    r = c.post(f"/v1/reports/dashboards/{BOARD}/guest-token", headers=reader)
    ok("and given a guest token for it", r.status_code == 200 and r.json().get("token"), f"{r.status_code} {r.text[:200]}")
    s = pod(r1, "embedded", str(board_id), r.json()["token"])
    ok("which opens the board in Superset, which nothing opens without it",
       s.get("with_token") == 200 and s.get("without") in (401, 403), s)
    r = c.post(f"/v1/reports/dashboards/{BOARD}/guest-token", headers=token("nobody@r1.test"))
    ok("a person with no reports right is refused the token", r.status_code == 403, f"{r.status_code} {r.text[:160]}")
    lower = token("reader@r1.test", **{clearance_claim: "PUBLIC"})
    r = c.get("/v1/reports/dashboards", headers=lower)
    offered = r.status_code == 200 and not any(d.get("slug") == BOARD for d in r.json())
    r = c.post(f"/v1/reports/dashboards/{BOARD}/guest-token", headers=lower)
    ok("a clearance below the identity's is offered nothing and refused the token (404)",
       offered and r.status_code == 404, f"{r.status_code} {r.text[:160]}")


def main(argv: list[str]) -> int:
    if argv[:1] == ["plan"]:
        print("\n".join(f"{n}. {step}" for n, step in enumerate(PLAN, 1)))
        return 0
    if argv[:1] == ["run"]:
        run()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
