# Docs lane · first brief · the website, from what is merged and the design reference

Written by the orchestrator, 7 November 2026, on the owner's word ("Docs: first brief"), after the first
feature merges (P7). Sonnet. Size M.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 9 above all: no real data, no real names, nothing from
outside this repository); ADR-142 (P7); ADR-143 to ADR-145 for what is coming; `FDE_HANDOVER.md` §1
(British English, the owner's tone).

**Do.** Bring `OspreyFlow_Build/marketing_site/deploy/` up to date:
1. A **drawing boards** section as the headline feature, from ADR-143 and the navigation prototype
   (`spec/glass_redesign/navigation_prototype.dc.html`), every claim marked **"coming"**: nothing of it is
   built yet.
2. **Three places** (the Glass, the Ingest Studio, Admin) from ADR-145, marked "coming".
3. What *is* merged may be described as built: the alerts journey's map is a design document, not a
   feature, so do not claim it.
Screenshots: none new tonight (no lane has merged a screen); reuse existing assets only, and say in your
report which pages need new captures once L2.2 and the boards merge.

**Never:** run `publish_pages.sh` or push anything, anywhere (ADR-142: lanes never push; the website is
public when published, and only the owner publishes it). Never touch `OspreyFlow_presentations/` (it is
not in git, so it is not in your worktree). Do not edit the guides (`OspreyFlow_Core/docs/**`) yet: they
follow merges, and none affects them tonight.

**Files.** `OspreyFlow_Build/marketing_site/**` only, plus your friction fragment and report.

**Exit.** The site's pages render locally (open `OspreyFlow_Build/marketing_site/deploy/index.html` in a browser, or serve the folder with
`python3 -m http.server` from it), every new claim marked "coming", British English throughout, no broken
local links; a friction fragment.

**Report** (Prompt L's format, at most twenty lines, also in this folder's `REPORT.md`): what changed per
page; which claims are marked coming and why; the pages needing new captures later; questions for the
owner as multiple choice; whether anything of yours is still running. Then stop.
