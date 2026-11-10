"""Which rule rights each demo account holds, and one recipe's Runs (UPG run 1, step 3). As run, with the
imports sorted and line breaks added for lint only."""

import os

import httpx
import upg_check

O = "http://osprey-upg.localhost:8090"
I = "http://id.osprey-upg.localhost:8090"
PID = "01M73BSY9PQFTW7B3VQY8Y75Q2"
for who in ("admin", "analyst", "engineer"):
    t = upg_check.sign_in(
        O, I, f"osprey-demo-{who}", os.environ[f"OSPREY_DEMO_{who.upper()}_PASSWORD"]
    )
    h = {"Authorization": "Bearer " + t}
    r = httpx.get(O + "/v1/me/rights", headers=h).json()["rights"]
    names = {
        x if isinstance(x, str) else (x.get("right") or x.get("id") or x.get("name"))
        for x in r
    }
    held = {k: k in names for k in ("author_rules", "deploy_rules", "triage_alerts")}
    print(f"upg-check: {who}: {held}")
    if who == "engineer":
        recs = httpx.get(
            O + f"/v1/investigations/{PID}/ingest/recipes", headers=h
        ).json()
        print("upg-check: recipe keys", sorted(recs[0])[:12])
        rid = recs[0].get("id") or recs[0].get("recipe_id") or recs[0]["recipe"]["id"]
        runs = httpx.get(
            O + f"/v1/investigations/{PID}/ingest/recipes/{rid}/runs", headers=h
        )
        print(
            f"upg-check: engineer: recipe {recs[0].get('name')!r} runs -> {runs.status_code}: {upg_check._summary(runs.json())}"
        )
