# studio-b · L1.6 plan (8 November 2026)

Spec: ADR-140 Amendments 9 (d3), 11, 12 (on lane/studio); redesign plan phase 9; 09 §2, §9; ADR-133 (lists today).

**A. Schemas (own commit, head).** `schemas/sources.py`: connection kinds `sql`, `api`, `json` with typed
settings (a secret named, never held); a source's `read` (SQL table, API path, JSON records path: a dotted
name, no expression, rule 8). New `schemas/list_connector.py`: templates (OFAC SDN, OFSI, UK Sanctions List,
UN, EU, OpenSanctions, blank), a blank mapping by column picks only, a deployment-wide list, an import's
outcome, a dataset's subscription by list id, an offered list.

**B. The screening-list connector** (`services/ingest/connectors/screening_templates.py`,
`services/api/list_connector.py`): template → the one screening shape; deployment-wide import writing
`reference_lists/deployment/<name>@v<n>.parquet` (Amendment 11's path), a new version only when the rows
change; per-dataset subscription by id; schedule and *Refresh now*; a dataset's own list imported from its
own files, replacing L1.4's stand-in. Routes under the Studio's Sources.
Tests first: each template maps its synthetic golden file; the blank template; import idempotent per
version; only subscribed lists offered; another dataset's list never offered; rule 4 on every route;
store and in-memory twin refuse the same things.

**C. Connectors** (`services/ingest/connectors/{sql,api,json}_connector.py`): each read lands as a CSV in
the dataset's folder, so the run path, watch, watermark and confinement stay as built; SQL read-only login
checked, TLS, incremental cursor; API base URL, bearer secret, pagination, egress host allow-list; JSON file
pattern + records path. Fixtures refuse what the real thing refuses (rule 15). Exit: `visit_bookings` from a
fixture Postgres, incremental; a refresh loads only new rows (live, under a lease).

**D. Glass:** Sources tab's screening lists and subscriptions; the wizard's new connection kinds;
keyboard cases (rule 13), registry ids as a diff; axe in dark, light, GOV.UK.
**E. Spec:** ADR-140 Amendment 13 (reservation asked), 09 §2/§9.
