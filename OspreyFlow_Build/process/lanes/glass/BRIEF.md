# Glass lane · brief L2.4, part 1 · Admin regrouped into sections

Written by the orchestrator, 7 November 2026, after L2.3's merge (`d4fe5e5`). Opus, medium. Size M. Part 2
(the Datasets section's *Highest marking it may hold* and *Promotion of drawn items* columns, ADR-145
decision 8) waits for Lane 3's L3.1, whose fields it reads; I will tell you when it lands.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4 and 13 above all); ADR-145 decisions 5 and 13, A1, O4;
ADR-110 Amendments 1 and 14 (Admin as a place, in sections; each section keeps the right its tab
required); ADR-112 (rights); `spec/02_GLASS_FRONTEND.md`'s Admin area; the navigation prototype (*Signed
in as* Administrator).

**Build.** The Admin place as a side list of sections, each shown only to a holder of its right (ADR-145
decision 5):
- **People:** People and roles; Roles; Dashboard identities.
- **Data:** Datasets; Connections.
- **Running:** Operations; System.
- **Policies:** Grading scheme; Approval rights; Uploads.
- **Audit.**
- **Demo packs.**

Today's tabs move into their sections unchanged. A section with nothing built yet (Roles, Grading
scheme, Uploads, Audit) is shown as a "coming" placeholder, and only to holders of its right. Under the
GOV.UK brand the list is a GOV.UK side navigation (decision 13).

**Tests first.**
- Every section shows only with its right, **and** each section's routes refuse a principal without it.
  The test is red with the routes' check removed; hiding alone must not pass (rule 3). Take the place
  test's approach from L2.2: the routes' full checks, not a hand-kept list.
- Keyboard cases in `keyboard/admin.spec.ts` for moving between sections, each red with its handler
  removed (rule 13). Send me the registry ids as a diff; I land them with your merge.
- Axe in dark, light and GOV.UK.

**Files.** The Glass lane's map (`admin/**`, `shell/**`). `spec/02` in the same commits.

**Exit.** Every section shows only with its right; `keyboard/admin.spec.ts` and axe green; `spec/02`
updated; a friction fragment. **Report** (at most twenty lines), with questions for the owner sent to me
by message.
