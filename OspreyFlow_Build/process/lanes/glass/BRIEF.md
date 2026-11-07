# Glass lane · brief L2.2 · three places: the switcher, the context banner, Home, the rail

Written by the orchestrator, 7 November 2026, on the owner's word ("Glass: L2.2"). Opus, medium. Size L.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 14 as ADR-142 rewords it; 3, 4 and 13 above all);
ADR-145 decisions 1–3 and N1–N6, with ADR-132 Amendments 5 and 6 (the GOV.UK header) and ADR-110
Amendment 14 (Admin as a place); ADR-112 (rights); `spec/02_GLASS_FRONTEND.md` §2.0 ("there is no
application switch", which this step replaces) and the shell sections; the design reference,
`spec/glass_redesign/navigation_prototype.dc.html` (navigation *B*). Where the prototype and ADR-145 differ,
ADR-145 governs.

**Build** (ADR-145 decisions 1–3):
1. **Three places.** *The Glass* (Case · Boards · Monitoring), *Ingest Studio* (1 Model · 2 Sources ·
   3 Pipelines · 4 Runs) and *Admin*. A switcher in the top bar lists only the places the person's rights
   open (N6); Home lists the same as cards. The Glass's rail loses *Ingest Studio*, *Admin* and *Proposed
   types*. The Studio has no rail. *Boards* may be a placeholder ("coming") until Lane 3 builds it.
2. **The context banner**: one line under the top bar, as decision 2 words it, with the cross-link for a
   person holding both the Glass and the Studio that keeps the case they came from.
3. **Under the GOV.UK brand**: the switcher inside the GOV.UK header (`brand/govuk/GovukHeader.tsx`);
   the banner a GOV.UK notification banner. Check the pinned `govuk-frontend` (6.6.0) offers header
   navigation; if not, a small local extension, recorded in an amendment you reserve with the orchestrator.

**Not in this step:** the case screen's lightening (L2.3), Admin's sections (L2.4), any alerts change.

**Tests first.** The switcher shows only the places a principal's rights open, **and each hidden place's
routes refuse that principal** (red with the routes' check removed: hiding alone must not pass; rule 3).
Keyboard cases in `keyboard/shell.spec.ts` for the switcher, the banner's cross-link and Home's cards,
each shown red with its handler removed (rule 13). Axe in dark, light and GOV.UK.

**Files.** The Glass lane's ownership map (`shell`, `layout`, `home`, `welcome`, `admin`, `statusbar`,
`theme`, `brand`). The Studio's own top (`ingest/**`) is Lane 1's: if the banner needs a hook there, ask
the orchestrator. `keyboard/actionRegistry.ts` and `tokens.css` go through the orchestrator. Update
`spec/02` §2.0 in the same commits (rule 11).

**Exit.** Each role sees only its places, and the hidden places' routes refuse it; `keyboard/shell.spec.ts`
and axe (dark, light, GOV.UK) green; `spec/02` rewritten; the DEMO_GUIDE chapters that name the rail's
entries say what moved (`OspreyFlow_Core/DEMO_GUIDE.md`, text only); a friction fragment.

**Report** (Prompt L's format, at most twenty lines, also in this folder's `REPORT.md`): each exit
criterion with its proving test; the commits; requests to the orchestrator; questions for the owner as
multiple choice; one hand check (full commands and where to click, as an analyst, a data engineer and an
administrator, default and GOV.UK); whether anything of yours is still running. Then stop.
