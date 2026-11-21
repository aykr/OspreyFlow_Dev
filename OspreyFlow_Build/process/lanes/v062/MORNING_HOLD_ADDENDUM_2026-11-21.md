# Addendum to the morning hold list (written after midnight; fold into `MORNING_HOLD_2026-11-21.md` when no merge is running)

## 7. DC1b (the two websites) stopped at round 4 of 4 with four faults: one line needed (`DC1b	add-round	<date>`)

The verifier checks every changed sentence against DC1a's table and has held the slice to it each round; round 4 found:

1. `overview.py` line about 346: the animated overview's audit scene (shown on both Homes) still has the heading **"Everything is on the record"**, stronger than DC1a found true.
2. `overview.py` line about 340: the same scene still draws an audit entry **"Refused: a read above their clearance"**: DC1a found that only refusals of case access are audited, and that records above a person's clearance are filtered in the store, not refused and recorded; the slice's own corrected sub line contradicts the drawn row.
3. `build.py` lines about 628 and 599: the net Home's "Inside your boundary" panel and the Governance "Data sovereignty" line still say the only traffic out is the install's downloads and an opt-in hosted engine; DC1a found model pulls on every start, a certificate fetch on an https address, and (v0.6.1) the dashboards' usage image. The constraint card and public-sector card were fixed; these two places were missed, and the test does not require the words there.
4. **The deliverable is missing:** the brief requires `DC1B_SENTENCES.md` (every replaced sentence, page, why it was too strong, replacement) plus the whole diff and a rendered copy of each changed page in `Claude outputs/ospreyflow_intent_2026-11-20/DC1b/`; the builder could not write there (the folder is outside its tree), and the list is in neither the commit nor a folder. **I will put the diff, the sentence list and the rendered pages in `OspreyFlow_Build/process/lanes/v062/slices/DC1b_OUT/` (inside my own area) when the slice is verified, for you to copy.**

**Recommendation: one add-round line.** All four are concrete and small (two scene strings, two lines of wording and a test requirement, a file). If you add it, round 5 fixes them and also makes the test require the corrected words in every place the claim appears, so a fifth miss cannot pass.

## 9. Slice D2 merged; which stage 4 builds it unblocks (your addition 2): partly, and one question

D2 (`74a983e`) moved the ingest, sources, releases clients. **`admin/api.ts` was left in the workspace** (the builder stopped at it because it imports `help/roles.ts`, which imports `shell/placesByRole.json` and has about ten importers, several React), so the "admin clients" the ADR names are not all in the package yet. Scout of the code (read, not measured):
- **Ready now (clients already in the package):** IS3 (the read-only dataset map: its data hook is in the package), IS5's Releases, Sources, Register and Screening lists, Publish, Profile and Checks screens.
- **Not ready on D1 and D2 alone, against your reading:** **IS2** (Model step: the link-type and proposal clients `linktypes/*` are in D3b); **IS5's Runs grid** (needs `boards/promotionsApi`, D3b; and `ExternalOrchestration.tsx` makes four inline fetch calls with no client module, D3c); **IS5 Verify** (`ontology/schema`, which needs E's types; it waits for GG2 in any case); **AD3 and AD4** (not described in any record I can read, and `admin/api.ts` is still in the workspace).
- **GR2 to GR4 and RM1** need D3a (reports, export, alerts, patterns clients) and D3b (`analytics/api`); GR2's Home needs `home/homeData.ts` and `home/guides.ts`, which are mixed with React/the DOM and need a split first (D3c).
**Question:** (a) **cut D3c to include moving `help/roles.ts` and `shell/placesByRole.json` and then `admin/api.ts`** (this touches AD1a's generated `placesByRole.json`, which your earlier ruling lets AD1a change once; I recommend D3c does it after AD1a is settled, so the two never edit it at once), or (b) leave `admin/api.ts` in the workspace and have the Admin pages import it from there until E. **D3 was cut three ways (D3a reports/alerts/patterns/export, D3b link/inspector/views/boards/others, D3c the files needing a split first, then the stray `export/api.ts.bak`) on the scout's measure: the rest of D3 is 2.5 times D2.** Nothing the ADR names is dropped.

## 8. DC1c (the README and four guides) stopped at round 4 of 4: three faults and a gap, one line needed (`DC1c	add-round	<date>`)

The verifier held every changed sentence to DC1a's table. What is left:
1. `OspreyFlow_Core/docs/user-guide.md` line about 22: the Software sovereignty line says "every software dependency is under an open-source licence. Model weights, map data, fonts and base images are outside the check that holds that", which a reader takes to mean everything else is inside the gate; the README and administration guide were corrected in round 3, this one was missed.
2. `OspreyFlow_Core/docs/architecture-guide.md` line about 29: "each store or engine sits behind a port (section 2), so replacing one is one adapter and one line of configuration" is untrue of PostgreSQL (the audit table and export ledger), Valkey (the working set) and OpenSearch, which are not behind a port.
3. `architecture-guide.md` line about 28: "software you can replace means a supplier's change of terms never holds your records hostage" implies supplier software holds records hostage (your rule: do not characterise proprietary tools) and says "never".
4. A test gap: the test flags an unlimited licence-gate claim only when the passage says "on every change"; the user guide's wording gets past it.

**Recommendation: one add-round line.** All concrete and small; round 5 fixes the three sentences and widens the test to the shape the text actually takes. DC1b's and DC1c's end state is the same: verified, held for your line, never merged without it. (The slice's deliverable folder, diff and rendered copy are written by me into `OspreyFlow_Build/process/lanes/v062/slices/DC1c_OUT/` when it is verified, because builders cannot write to `Claude outputs/`.)

## 8b. PL4d2 merged (`74a983e`), LR1 merged (`7479243`)

No action needed from you.
