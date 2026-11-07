# Glass lane · brief L2.4, part 2 · Admin › Datasets and System

Written by the orchestrator, 7 November 2026, after part 1's merge (`d035223`). **Do not start it yet:** it
waits for Lane 3's L3.1 on `main` (its fields), and I will tell you when that lands. ADR-145 Amendment 4 is
already on `main` (`ba8a194`). Opus, medium. Size L.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 7 and 13 above all); ADR-145 decision 8 and Amendment 4
decisions 6 and 7; ADR-143 Amendment 2 decisions 1 and 2; ADR-112 Amendments 4 and 5 (rights; a service
account owns nothing); `spec/02_GLASS_FRONTEND.md`'s Admin area.

**Build.**
- **Admin › Datasets**, one row per dataset: its kind (*Source*, *Composite*, *Drawn*), unit, highest
  marking it may hold, promotion policy; its **Authors** (people, a team, or both) and *Change owner…*
  (the same choice *Make live* offers, refused for a service account, audited); **every linked case**
  with its layer's item count, size and state (open, removed); for a removed case, *Merge into the
  dataset* and *Delete*, each with its dry run (the actions themselves are L3.4's; here, the entries
  and their refusals). **Never a layer's contents:** no item, label or property on any route.
- **Admin › System: *Dataset owners may be*** people and teams (the default), people only, or teams only;
  it governs *Change owner…* here and *Make live* in L3.1b.
- Teams arrive with L2.5. Until then *Change owner…* offers people only, and says so.

**The hard parts (name them in your plan).** The layer counts are a new read across cases: an
administrator sees counts for cases they are not a member of, and nothing else. Prove no route returns an
item, label or property, red with one label added to the response. Counts are taken by the store, not
filtered in the Conduit (rule 3). A removed case's row must not reveal more than an open one's.

**Tests first.** Each column's route refuses without its right (the section's right from Amendment 3);
the counts-only test above; *Change owner…* refused for a service account and against the System
setting; keyboard cases in `keyboard/admin.spec.ts` for *Change owner…*, the System setting and each
removed-case entry (rule 13; registry ids to me as a diff); axe in dark, light and GOV.UK.

**Carried from part 1's review.**
- The routes test in the reverse direction: a holder of the right alone is answered (Proposed types'
  `require_admin_role`; the schedule preview, which also answers `operate_schedules`).
- The place-test helper gap the review named.
- REPORT at most twenty lines.

**Exit.** ADR-145 Amendment 4's Datasets and System tests green; no layer contents on any route;
`spec/02` updated in the same commits; a friction fragment; the report, with questions for the owner
sent to me by message.
