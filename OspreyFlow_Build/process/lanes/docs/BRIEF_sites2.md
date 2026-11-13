# Docs lane · brief sites2 · the approved site design adopted in marketing_site (M–L)

Written by the orchestrator, 13 November 2026 evening, at the owner's word, as part of the "docs · sites" step. For a
**docs session on `sol`**, branch `lane/docs-sites2` from main. Opus, medium. R1, GitHub CI and the v0.5.1 release keep
priority for the server, merges and reviews; **this step needs no server** until the screenshots (step 8 below), and
**does not merge until the orchestrator has cut v0.5.1's release candidate**.

## Read first

1. `Claude outputs/ospreyflow_sites_2026-11-13.zip` (outside the repository, beside it at the repository root):
   `HANDOVER.md` first, then the two sites and `source/`. Unpack it into a scratch folder, never into the repository.
2. Your own sites step as merged (`OspreyFlow_Build/marketing_site`, its generator, its tests, the 12 November
   decisions in this folder's `BRIEF.md`).

## The owner's instructions (13 November)

1. **Adopt this design and structure** for both sites in `OspreyFlow_Build/marketing_site`. It supersedes the look of
   the 12 November drafts. **It does not supersede facts already corrected:** where your Features, Get started or UK
   public sector text differs, yours wins.
2. **One generator as the source** (the existing one). Bring in the overview animation, the GOV.UK animation, the palette
   and the script; the generated pages stay committed, with the drift test.
3. **HANDOVER.md's "What the build still has to do":**
   - **fonts:** vendor Atkinson Hyperlegible Next and IBM Plex Mono (SIL OFL) with their licences in the repository, and
     add `@font-face`. There must be no external request;
   - **facts:** check every chapter of both animations (eleven overview chapters, four GOV.UK steps) against main and
     the guides, and record each check;
   - **tests:**
     - the wording rules inside the animations' text;
     - no external request;
     - the theme switch;
     - the player: it advances, pauses, respects reduced motion, and stops off screen;
     - every text pairing in both palettes at 4.5:1;
     - keyboard and accessibility scans in both themes;
   - **the inline `<head>` script:** hash it for the CSP rather than accept a flash;
   - **the Solirius Reply assets:** record where the two logos and two photographs came from (the current site's
     bundle), and that their use is the owner's instruction.
4. **The rules:**
   - the GOV.UK animation has no crown, no GOV.UK logotype and no GDS Transport (Arial), with the line under it;
   - no client, no competitor and no Laurium is named;
   - the data is synthetic only;
   - "Designed to meet the GDS Service Standard", with the three checks, wherever the Standard is named.
5. **The datasets chapter (the orchestrator's answer, for you to build):** a dataset has **no version number of its
   own**. These are versioned:
   - its **domain model**: a live version, an open draft, and earlier versions restorable (`DatasetModelView`,
     `RevertModelInput`);
   - each **recipe**, by `recipe_version`. Ingest Studio says "recipe", not "pipeline"; check what Admin calls it;
   - **every load**, recorded by `load_id` with the recipe version that made it, and revertable.

   The chapter's current text never versions a dataset, but "Pipeline v3" and "each pipeline" should read as the
   product says.

   **Proposed sub-line:** "Every load is recorded with the recipe version that made it, and can be reverted. The
   dataset's model is versioned: one live, one draft, and every earlier version can be restored."

   **Drawing:**
   - the timeline of loads, each tagged "recipe v3", one struck through as reverted;
   - a model card "Model v14 · live / v15 · draft";
   - no version on the dataset itself.

   Also check, against the code:
   - "Merges are reviewed by a second person": the promotion policy and `review_promotions`. Is a second person
     required, or can a policy allow one?
   - "Highest marking: OFFICIAL-SENSITIVE": is that a marking the product draws, or a caveat?
   - "Drawn items merge into a dataset as a load of their own".
6. **Keep the owner's standing decisions:**
   - Couldridge;
   - servicecentre@solirius.com, with "Put 'OspreyFlow security' in the subject";
   - the "How it is built" paragraph;
   - six names on the Team page only;
   - the neither-site-names-Laurium test.
7. **Do not build "Not decided, so not built".** The orchestrator has given the owner its view.
8. **Screenshots** (needs the frozen demo, so the server): later, on the orchestrator's word.
9. **No repository created, nothing published,** and the current six-page site unchanged, all until the owner says.

## Report

Send ready-to-merge to the orchestrator, with:
- every fact you changed or confirmed: chapter, claim, source (file:line or guide §);
- the font licences' paths;
- the tests, each red first.
