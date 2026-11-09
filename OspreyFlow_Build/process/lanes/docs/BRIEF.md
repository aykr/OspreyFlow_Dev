# Docs lane · brief D2a · the README, the guides, the welcome pages and the website, as built

Written by the orchestrator, 9 November 2026, for a **fresh docs session on the default account** (`ayan`). **The
owner's ruling of 9 November, about 21:35:** D2a starts now, leaving out the alerts and rules pages until rules'
L2.10 is merged and deployed (it relaxes the earlier gate, "after L2.9, L2.10, L2.5, P1 and P3 run deployed").
Read `process/BUILD_PLAN_PARALLEL_LANES.md`'s D2a section, `FDE_HANDOVER.md` §1 (British English, the owner's tone)
and the merged reports in `process/lanes/*/REPORT.md` first. Sonnet or Opus, medium. Size M.

**The lane.** The docs row: `OspreyFlow_Core/docs/**`, `OspreyFlow_Core/README.md`, `apps/workspace/src/welcome/**`,
`OspreyFlow_Build/marketing_site/**`. Never `OspreyFlow_presentations/` (D2b). Never run `publish_pages.sh` or push
anything, anywhere: the website is public when published, and only the owner publishes it. Docker is off on this
Mac, so take no new screenshots tonight; list in the report which pages need captures once a deployment runs.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 9 above all: no real data, no real names, nothing from outside this
repository); the spec as merged; describe only what is on `main` as built, and mark anything else "coming".

**Do now:**
1. **The README** (`OspreyFlow_Core/README.md`) as the plan says (the overview deck's lasting content, as built). It
   is published, so it stays a draft for the owner to approve: say so at its head.
2. **The user, developer and administration guides, and a standalone architecture guide** (`tools/docs_pdf.py`):
   everything the plan lists **except** the alerts and rules module (one queue, what raises alerts, watches, team
   routing, Raise an alert, the rule editor), which waits for L2.10 and L2.11. Include: four places; no branches;
   home cases, Authors and teams; releases; the Reports Viewer's journey; Maps and Models administration; the roles'
   words from `help/roles.ts`; Disable and ownership as far as L3.8 built them; the backups folder as ADR-114
   Amendment 37 decides (it is being built: "coming" until it merges); `spec/10_ADMINISTRATION_GUIDE.md`'s missing
   §9.5 and §9.6.
3. **The welcome pages, the website and the GOV.UK wording**, brought into line with one another and the guides.
   The website marks unbuilt features "coming".

**Exit.** The guides build to PDF (`tools/docs_pdf.py`); the docs gates green (`make citation-check
product-tree-link-check provenance-annotation-check demo-guide-check`, and `make ci`'s docs checks); every claim
traceable to a merged report or the spec; a friction row; the report names what waits for L2.10 and L2.11.
