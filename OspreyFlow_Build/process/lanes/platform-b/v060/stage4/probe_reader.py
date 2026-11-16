"""Probe (the owner's ruling, 16 Nov): can a Reports Viewer's own chart, over a dataset it reaches, return
rows beyond its row-level access? Run in R1's api pod beside superset_pod.py (its sessions, its client).
Synthetic data on a throwaway install; prints the `dashboard` values each read returns, never a figure."""

import json
import sys

sys.path.insert(0, "/tmp")
import superset_pod as sp  # noqa: E402

GLASS = sys.argv[1]
out: dict = {}

# The administrator's dataset and chart over the mart (as row 3 would make them), on board 1.
made = sp.chart(GLASS, "admin@r1.test", "1")
out["admin chart"] = made
dataset, chart = str(made.get("dataset")), str(made.get("chart"))

# The same chart's data read with each person's own Superset session.
for hint in ("admin@r1.test", "builder@r1.test", "reader@r1.test"):
    out[f"chartdata session {hint}"] = sp.chartdata(GLASS, "session", hint, "1", dataset, chart)

# Each of builder and reader makes their own chart on the dataset, then reads it.
for hint in ("builder@r1.test", "reader@r1.test"):
    client = sp._client(GLASS, hint)
    token = sp._csrf(client)
    write = {"X-CSRFToken": token or "", "Referer": f"https://bi.{GLASS}/"}
    params = {"viz_type": "table", "groupby": ["dashboard"], "metrics": ["count"], "row_limit": 1000}
    own = client.post("/api/v1/chart/", headers=write, json={
        "slice_name": f"probe {hint}", "viz_type": "table", "datasource_id": int(dataset),
        "datasource_type": "table", "params": json.dumps(params)})
    sp._keep(client, hint)
    entry = {"made": own.status_code, "said": own.text[:160]}
    if own.status_code == 201:
        entry["read"] = sp.chartdata(GLASS, "session", hint, "1", dataset, str(own.json()["id"]))
    # The dataset's rows asked directly (no chart): what the dataset alone gives this session.
    body = {"datasource": {"id": int(dataset), "type": "table"}, "force": True,
            "queries": [{"columns": ["dashboard"], "metrics": ["count"], "row_limit": 1000}],
            "result_format": "json", "result_type": "full"}
    direct = client.post("/api/v1/chart/data", json=body, headers=write)
    rows = [r for q in (direct.json().get("result", []) if direct.status_code == 200 else []) for r in q.get("data", [])]
    entry["dataset direct"] = {"status": direct.status_code, "dashboards": sorted({str(r.get("dashboard")) for r in rows})}
    out[f"own chart {hint}"] = entry

print(json.dumps(out, indent=1))
