# DC1c, at round 7 of 7: every case, open or closed (the line's table before a round of 5 or more; a read-only scout's, 22 November 2026)

Rounds are the verifier's: R1 `3ac0b21`, R2 `5e0593b`, R3 `eac9bbd`, R4 `7b90951`, R5 `3fa5147`, R6 `55f0a28`, R7 `229069b`. Paths are under `OspreyFlow_Core/` or `OspreyFlow_Build/` as written. "Closed" means a later commit message or a later round shows the fix; "not re-raised" is inferred (the scout read no tip file). **This round is a send-back at no cost for one thing: the conflict with main** (`records` state: `phase building, round 7, refused_for conflict`); **the slice was accepted narrower at `229069b9bb`.**

| Round | Kind | File and line | What | Status | Cause |
| --- | --- | --- | --- | --- | --- |
| R1 | fault | `OspreyFlow_Core/docs/architecture-guide.md:39` | The route-out sentence says only configured features need one | not re-raised; inferred closed | overstatement |
| R1 | fault | `OspreyFlow_Core/docs/user-guide.md:27` | Privacy bullet stated as fact | closed (R4, 7b90951) | overstatement |
| R1 | fault | `OspreyFlow_Core/docs/architecture-guide.md:31` | "Checks every Python package"; the gate reads build metadata only | not re-raised; inferred closed | overstatement |
| R1 | fault | `OspreyFlow_Core/docs/architecture-guide.md:46` | Superset pixel "from its maker's address" is Scarf's gateway | not re-raised; inferred closed | unsupported attribution |
| R2 | fault | `OspreyFlow_Core/docs/administration-guide.md:32` | Unqualified "clearances set the limit" claim (also README, developer guide) | not re-raised; inferred closed | overstatement |
| R2 | fault | `OspreyFlow_Core/docs/administration-guide.md:34` | "Exports go in a ledger" with no limit | not re-raised; inferred closed | overstatement |
| R2 | fault | `OspreyFlow_Core/docs/user-guide.md:21` | Licence line omits weights, map data, fonts, base images | closed (R5, 8444177) | overstatement |
| R2 | fault | `OspreyFlow_Core/docs/architecture-guide.md:333` | Section 9 says every avoided component was replaced; the Grafana row says only "unbundled" | not re-raised; inferred closed | table and prose differ |
| R2 | test gap | `OspreyFlow_Build/tests/test_intent_in_the_guides.py:192` | `new_text` scans less than its docstring says | no closure record shown; not re-raised | test scope |
| R3 | fault | `OspreyFlow_Core/README.md:20` | "Every software dependency checked on every change" overstates the gate | closed (R4, R5) | overstatement |
| R3 | fault | `OspreyFlow_Core/docs/architecture-guide.md:275` | "Every change audited": only mutations are | closed (R4) | overstatement |
| R3 | test gap | `OspreyFlow_Build/tests/test_intent_in_the_guides.py:239` | Privacy check passes a fact-stated bullet if "aim" and "gap" appear anywhere | closed (5682fbc) | test shape |
| R4 | fault | `OspreyFlow_Core/docs/architecture-guide.md:29` | "Each store or engine sits behind a port" untrue for PostgreSQL, Valkey, OpenSearch | closed (R5, 8444177) | overstatement |
| R4 | fault | `OspreyFlow_Core/docs/architecture-guide.md:28` | "Never holds your records hostage" breaks the open-source-merits rule | closed (R5, 8444177) | absolute claim |
| R4 | test gap | `OspreyFlow_Build/tests/test_intent_in_the_guides.py:254` | Licence check looks only for "on every change" | closed (R5, ac5a01) | test shape |
| R5 | test gap | `OspreyFlow_Build/tests/test_intent_in_the_guides.py:251` | Port regex misses "behind ports" and "all the stores" | **no closure shown** | test shape |
| R5 | fault | `OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md:18` | Relative link to the architecture guide dead from `spec/` | closed (R6, 55f0a28) | stale pointer |
| R6 | fault | `OspreyFlow_Core/README.md:101` | "Architecture guide's section 2 says which is which" points at a section that says everything crosses a port | closed (R7, 229069b) | stale pointer |
| R6 | fault | `OspreyFlow_Build/process/lanes/v062/slices/DC1c_OUT/DC1C_CHANGES.md:38` | Round-6 rows after a blank line do not render as table rows | closed (R7, 229069b) | tracking-document error |
| R7 | test gap | `OspreyFlow_Build/tests/test_intent_in_the_guides.py:274` | `PORT_CLAIM` cannot match "everything crosses/passes between … port" or "every read through the ports"; no red case plants them | **OPEN (R7's record)** | test pattern |
| gate | conflict | `OspreyFlow_Core/docs/administration-guide.md`; `docs/pdf/{administration,architecture,developer,user}-guide.pdf`; `docs/pdf/manifest.json` | The branch conflicts with main: PL7a1 and DC1c both appended change-table rows 2.30 to 2.33 | **OPEN: this round** | two slices appended the same rows |

**Totals:** 22 verifier findings over seven rounds (17 faults, 5 test gaps) plus one merge conflict. **Open now:** (a) the conflict (this round's work: the brief's Round 8 section: take main in, keep both rows and renumber DC1c's, regenerate the PDFs and the manifest with `tools/docs_pdf.py --write`, change no approved sentence); (b) the R7 test gap at line 274; (c) the R5 gap at line 251; (d) the R2 gap at line 192 (b to d are already accepted narrower; they are backlog rows, **not this round's work**). **Convergence:** faults per round 4, 4, 3, 3, 1, 2, 0; the test gaps did not converge (raised in five of seven rounds): the sentences are settled, the test that guards them is not.
