# Studio lane · brief L1.2 · phase 6: the canvas as editor, the Map editor, guided mode

Written by the orchestrator, 7 November 2026, on the owner's word ("Studio: L1.2"). Opus, medium. Size L:
it may take a second session; stop at a clean, committed point and report what is left.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 14 as ADR-142 rewords it; 13 and 15 above all); ADR-140
and its Amendments 1–7; ADR-108 as amended by ADR-108 Amendment 6; `spec/09_INGEST_STUDIO.md`;
`spec/02_GLASS_FRONTEND.md` (keyboard, themes); the redesign's design reference,
`spec/ingest_studio_redesign/` (`INGEST_STUDIO_REDESIGN_BRIEF_v2.md`, `ingest_studio_prototype.html`,
`wf3_pipeline_canvas.svg`); and its build plan's **phase 6**,
`spec/ingest_studio_redesign/BUILD_PLAN_INGEST_STUDIO.md` (committed at `a56f2f9`). ADR-145 (the
Studio is its own place, with no rail; Lane 2 builds the switcher, so do not build one here).

**Build** (phase 6's "Do"): the drawer beside the canvas (`PipelineCanvas.tsx` and a new `NodeDrawer`),
never replacing it; *Preview* on any node (today's dry run up to that node: the node's table, or the
graph on Map and Load); *Test* for the whole pipeline (today's Verify); *Deploy as vN*. The **Map
editor**: pipeline strip, staged columns pane, template canvas (today's `MapScreen` canvas, kept),
inspector with bindings, match on, on match, link when, SAME_AS score; drag-to-bind and the keyboard path
(select both, Enter: a spec gap, close it in `spec/09` by amendment under a reserved number); unmapped
columns always shown; ◂ ▸ sample paging. **Guided mode**: the numbered list with the same drawers;
expert steps read-only; the mode a per-person preference. Every screen in dark, light and GOV.UK.

**Not in this step:** phase 5's target model (Lane 3's L3.1b); staging steps (phase 7); case views or
boards (Lane 3).

**Tests first.** A keyboard case in `keyboard/ingest-studio.spec.ts` for every new action (rule 13),
each shown red with its handler removed; axe in all three themes in `a11y/every-harness.spec.ts`; Preview
reads under the person's own principal (an access test: Preview of a node never shows a row the person
could not read, rule 4); `MapScreen` tests migrated, not deleted.

**Files.** The Studio lane's ownership map. `keyboard/actionRegistry.ts` and `packages/schemas/**` go
through the orchestrator as small shared commits (ask in your report and stop that piece). Reserve any
ADR or amendment number with the orchestrator before writing it. Take the lease for any live test.

**Exit.** Phase 6's exit: the Prison Intelligence reports pipeline can be built from scratch in guided mode
by someone following the demo script, and edited in expert mode; `MapScreen` tests migrated and green;
keyboard and axe green; spec 09 updated; a friction fragment.

**Report** (Prompt L's format, at most twenty lines, also in this folder's `REPORT.md`): each exit
criterion with its proving test; the commits; requests to the orchestrator; questions for the owner as
multiple choice; one hand check (full commands and where to click, default and GOV.UK); whether anything
of yours is still running. Then stop: no next step.
