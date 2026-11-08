# Carries between lanes

Requests one lane makes of another lane's files, kept by the orchestrator until the receiving lane's next brief
takes them (then struck through with the brief's commit). Newest last.

| For | Item | From | Into |
| --- | --- | --- | --- |
| admin | Remove Admin's *Proposed types* section: proposals are decided on the Studio's Model tab (ADR-090 Amendment 4) | case-b, L3.5 | L2.7 |
| admin | *Admin › Connections* gains the SQL and API connection settings' fields | studio-b, L1.6 | L2.7 |
| admin | ADR-144 decision 6's count on *Admin › System*: cases converted to views, with the migration's report | case, L3.2 | L2.5b |
| rules | The rule's list picker reads `GET /v1/datasets/{id}/reference-lists/offered`, so a rule offers only subscribed lists | studio-b, L1.6 | L2.10 or L2.11 |
| rules | Ask to search (`patterns/api.ts`) shows `model_limit_reached` as it shows `engine_refused` | platform, P2 | L2.10 (saved patterns) |
| case | L3.4: a withdrawal leaves in place a promoted link the withdrawer may not see (settled, `MORNING.md` item 60) | case, L3.3 | L3.4 |
| studio-b | Wire the subscribed list ids into `studio_staging` and `reference_list_import`, and retire L1.4's stand-in import, once L1.4 is on main | studio-b, L1.6 | after L1.4 |
| studio | L1.5 first: Test of a pipeline with no staging steps still counts over masked rows (pre-existing rule 3 oracle) | independent review of L1.4 | L1.5 |
| admin | The Model tab's proposal notifications (count, reminder, Needs you) for analyst-defined link types | case-b, L3.5 | L2.7 |
| case | Mount rules-b's alert badge overlay in GlassCanvas.tsx (patch in process/lanes/rules-b/) and the boards' Alerts panel | rules-b, L2.12 | L3.4 or at rules-b's merge |
| admin | Admin's tips (Roles, People, Datasets) from help/roles.ts (patch in process/lanes/rules-b/) | rules-b, L2.12 | L2.7 |
| rules | *See the trend* in the queue's detail opening the board filtered (patch in process/lanes/rules-b/) | rules-b, L2.12 | L2.10 or L2.11 |
