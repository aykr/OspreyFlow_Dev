# Platform lane · P1 · report (in progress)

**The owner's rulings, 8 November 2026** (relayed by the orchestrator, ospreyflow-7e):
- Q1 key storage: **B, the gateway's own database** (LiteLLM's admin API, encrypted, no restart). Not the lane's recommendation (A). ADR-135 Amendment 2 records the consequences: where the database lives, how its encryption key is supplied (never in osprey.yaml), backup and restore, what `ospreyflow models key` now does.
- Q2 engines and defaults: **A**, osprey.yaml stays the starting point; Admin's changes go into a separate models file read by the gateway, the Conduit, `ospreyflow models` and `apply`; keys never in it.
- Q3 second person: **A**, none; every change audited, never the key.
- Q4 the right: **A**, new `manage_models`, held by the administrator and grantable singly; ADR-112 Amendment 7 reserved for the lane; the rights change goes to the orchestrator as a shared commit first.
- harness/screens.py's egress warning: the orchestrator ratified the lane changing it.
