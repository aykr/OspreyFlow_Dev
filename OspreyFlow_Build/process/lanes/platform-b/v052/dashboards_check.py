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
5. **Embedding** (Amendment 11 point 8), through the Glass's door: the Reports Viewer is offered
   `r1-board` and given a guest token, which opens the board in Superset (and nothing opens without it).
   **Each refusal the Conduit's `may_open` makes is asked** (rules 3 and 4): no reports right is refused the
   listing and the token (403); a Reports Viewer with no level on the identity's case, one of another unit,
   and one whose clearance is below the identity's are each offered nothing and refused the token (404, the
   same as a board that does not exist).

**Run it through `r1_live.sh dashboards run`** (from OspreyFlow_Core), which gives it R1's own
environment: its kubectl, its kubeconfig, the kind platform's folder and the checkout's Python. Every kubectl
call names R1's namespace. No token, and no secret, is printed or recorded: a guest token is reported by its
status alone, and the report sync's secret reaches the Secret through kubectl's stdin, never its command line.

    bash ../OspreyFlow_Build/process/lanes/platform-b/v052/r1_live.sh dashboards run
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
    "Superset: the administrator, the builder and the Reports Viewer sign in as Admin, Alpha and Gamma, "
    "each Superset account the Conduit's principal (the object id)",
    "Superset: the administrator saves the board r1-board (or finds it, on a rerun)",
    "Superset: the builder saves a dashboard; the Reports Viewer is refused saving one (403)",
    "Superset: the person with no role is refused by Superset at sign-in (its /api/v1/me/ 401)",
    "Superset: a role is re-read at the next sign-in (the builder made a Reports Viewer: Gamma)",
    "embedding: the Reports Viewer is offered r1-board and its guest token opens it, nothing without",
    "embedding: no reports right is refused the listing and the token (403)",
    "embedding: no level on the identity's case, another unit, a lower clearance: offered nothing, refused (404)",
]


def report_sync_dashboards(client_id: str, secret: str) -> str:
    """The value INSTALL.md's step 6a has the client give the Terraform's `report_sync_dashboards`, one
    dashboard identity: `{"client_id", "secret"}` and nothing else (held to the runbook's own example by
    `tests/test_v052_dashboards_check.py`)."""
    return json.dumps([{"client_id": client_id, "secret": secret}])


def _r1() -> Any:
    sys.path.insert(0, str(GATES))
    import r1_kind  # platform's driver, imported, never changed here

    return r1_kind


def kube(r1: Any, *args: str, stdin: str | None = None) -> str:
    """kubectl in R1's namespace, always named: never whatever a kubeconfig's context points at."""
    return r1.kubectl("-n", r1.NS, *args, stdin=stdin)


def pod(r1: Any, *args: str) -> dict[str, Any]:
    """`superset_pod.py` in the api pod, its one JSON line back."""
    out = kube(r1, "exec", "-i", "deploy/api", "--", "/app/.venv/bin/python", "-I", "-", r1.GLASS, *args,
               stdin=POD_SCRIPT.read_text())  # fmt: skip
    return json.loads(out.strip().splitlines()[-1])


def run(r1: Any = None, ask: Any = None, sleep: Any = time.sleep) -> None:
    """The check; `r1` and `ask` (superset_pod's answers) are R1's driver and the pod, or a test's fakes, and
    `sleep` the wait between reads of the report sync's first pull (a test's waits nothing)."""
    import yaml

    r1 = r1 or _r1()
    ask = ask or (lambda *args: pod(r1, *args))
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
    # INSTALL.md's step 6a, exactly as the client is told: the Terraform's `report_sync_dashboards` given
    # `{"client_id", "secret"}` alone, applied into our Secret, and the report sync restarted. The run's
    # Terraform stand-in holds `[]` (r1_kind.py), so the apply's write is made here, in the shape it writes.
    given = report_sync_dashboards(app_id, secret)
    kube(r1, "patch", "secret", "ospreyflow-secrets", "--type", "merge", "--patch-file", "/dev/stdin",
         stdin=json.dumps({"stringData": {"REPORT_SYNC_DASHBOARDS": given}}))  # fmt: skip
    kube(r1, "rollout", "restart", "deploy/report-sync")
    kube(r1, "rollout", "status", "deploy/report-sync", "--timeout=10m")
    pulled = None
    for _ in range(60):
        listed = c.get("/v1/admin/dashboards", headers=admin).json()
        pulled = next((d for d in listed if d.get("client_id") == app_id), None)
        if pulled and pulled.get("last_pulled"):
            break
        sleep(10)
    ok("the report sync signs in with its app-only token and pulls the case (Admin › Dashboards)",
       bool(pulled and pulled.get("last_pulled") and not pulled.get("last_failure")), pulled)

    # 3 and 4. Superset's sign-in, its roles, building.
    for hint in ("admin@r1.test", "builder@r1.test", "reader@r1.test"):
        s = ask("signin", hint)
        ok(f"{hint} signs in to Superset as {SUPERSET_ROLE[hint][0]}",
           s.get("signed_in") is True and s.get("roles") == SUPERSET_ROLE[hint], s)
        # Superset keys its user by the Entra object id (Amendment 9): the Conduit's principal, not a name.
        ok(f"{hint}'s Superset account is the Conduit's principal (the object id)", s.get("username") == people[hint], s)
    s = ask("build", "admin@r1.test", "R1 board", BOARD)
    ok(f"the administrator saves the board {BOARD} (or finds it, on a rerun)",
       s.get("status") == 201 or (s.get("status") == 200 and s.get("existing") is True), s)
    board_id = s.get("id")
    s = ask("build", "builder@r1.test", "R1 builder's own board")
    ok("the builder saves a dashboard", s.get("status") == 201, s)
    s = ask("build", "reader@r1.test", "R1 refused board")
    ok("the Reports Viewer is refused saving one (403)", s.get("status") == 403, s)
    s = ask("signin", "nobody@r1.test")
    ok("the person with no reports right is refused by Superset at sign-in (its /api/v1/me/ 401)",
       s.get("signed_in") is False and s.get("stage") == "superset" and s.get("me") == 401, s)
    r = c.put(f"/v1/admin/people/{people['builder@r1.test']}/roles", headers=admin, json={"roles": ["reports_viewer"]})
    s = ask("signin", "builder@r1.test")
    ok("a role is re-read at the next sign-in (the builder, now a Reports Viewer, is Gamma)",
       r.status_code == 200 and s.get("roles") == ["Gamma"], s)

    # 5. Embedding, through the Glass's door. A guest token is reported by its status, never its text.
    def offered(headers: dict[str, str]) -> tuple[int, bool]:
        r = c.get("/v1/reports/dashboards", headers=headers)
        return r.status_code, r.status_code == 200 and any(d.get("slug") == BOARD for d in r.json())

    def guest(headers: dict[str, str]) -> tuple[int, str | None]:
        r = c.post(f"/v1/reports/dashboards/{BOARD}/guest-token", headers=headers)
        return r.status_code, (r.json().get("token") if r.status_code == 200 else None)

    reader = token("reader@r1.test")
    status, has = offered(reader)
    ok(f"the Reports Viewer is offered {BOARD}", status == 200 and has, f"listing {status}, offered {has}")
    status, guest_token = guest(reader)
    ok("and given a guest token for it", status == 200 and bool(guest_token), f"guest token {status}")
    s = ask("embedded", str(board_id), guest_token or "")
    ok("which opens the board in Superset, which nothing opens without it",
       s.get("with_token") == 200 and s.get("without") in (401, 403), s)
    nobody = token("nobody@r1.test")
    listing, _ = offered(nobody)
    refused, _ = guest(nobody)
    ok("a person with no reports right is refused the listing and the token (403, 403)",
       (listing, refused) == (403, 403), f"listing {listing}, guest token {refused}")
    unit_claim = claims["org_unit"]["claim"]
    for who, headers in (
        ("a Reports Viewer with no level on the identity's case (the builder, now Gamma)", token("builder@r1.test")),
        ("a Reports Viewer of another unit", token("reader@r1.test", **{unit_claim: "r1-another-unit"})),
        ("a Reports Viewer whose clearance is below the identity's", token("reader@r1.test", **{clearance_claim: "PUBLIC"})),
    ):
        listing, has = offered(headers)
        refused, _ = guest(headers)
        ok(f"{who} is offered nothing and refused the token (404)",
           listing == 200 and not has and refused == 404, f"listing {listing}, offered {has}, guest token {refused}")


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
