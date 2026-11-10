# rules-b lane · report · L2.11a, the rule's standards: BPMN 2.0 and DMN (10 November 2026)

1. **Export to `.bpmn` and `.dmn`, and import back to the same rule: met.** `tests/rule_standards/test_codec.py` has a round trip for every shape of every blank. The route's round trip, dataset included, is in `test_rule_standards_routes.py`.
2. **An unsupported file is refused in words, naming what it holds: met.** It covers a BPMN, DMN, `osprey:` or vendor element or attribute, an element out of its place, and an attribute the model would drop. Each is planted in a file the codec wrote (rule 15).
3. **Access (rules 3 and 4): met.**
   - **Export:** a rule the reader may not see is the same 404 as a missing one, offline and live (red with the store's reach dropped).
   - **Import:** `author_rules` at Author. The dataset must be the case's chosen source or composite; any other is the app's `dataset_not_found`.
   - **Caps:** both are red by plant.
   - **Tables:** the rights and levels rows (`author_rules` came off the not-yet list). The export's row in the wire census's `NON_JSON_ROUTES` is ratified with its proof: the XML states no figure (`test_an_export_states_no_figure_of_anything_the_reader_cannot_see`, red by four codec plants).
4. **Stored beside each version (ADR-146 Amendment 5, option (a)): the codec's half is met.** `rule_files` is the save's function, and Export serves stored bytes (red with it rendering). Rules wires the store in L2.11, with its two tests.
5. **Show as BPMN by keyboard and axe: met.** `ShowAsBpmn.test.tsx` passes (6). `keyboard/rule-standards.spec.ts` passes (4): Tab, open, Escape, Close, focus back, and Escape back to the editor, each red with its handler removed. Axe passes in three themes (12). A text-contrast plant stayed green, so that is a recorded gap (`gates/ed3e1d1.keyboard-axe.txt`).
6. **Red record:** `l2.11a/RED_RECORD.md` §1–§9. **Friction row:** `process/friction/2026-11-10-rules-b-rule-standards.md`.
7. **Live:** lease rules-b on stack d (server). Two runs at e81e8a2, then a second set at 7be4916 (`gates/`).
8. **Gates at d44e32d** (rebased onto fb704c4, L2.10 in; tree 5c5b983; no rebase onto 2456d2c, agreed). `gates/d44e32d.ci.txt` has only Docker red, and `gates/d44e32d.test.txt` has pytest at 10426 passed, 2 failed and 13 skipped, and vitest at 2943 passed and 1 failed; each failure is an environment one, explained there. Gating found three gaps, all fixed: the stale `ImportedRule.ts` (72f6a2d), spec 03's rows (the patch), and the census row.
9. **Lane-reviewer:** run once. It found eight must-fix and eight minor items; all are fixed except two left minors (decisions 8 and 9 below).
10. **Patches, applied unstaged for the gates:** `audit-L2.11a.patch` (regenerated after L2.10), `every-harness-L2.11a.patch` and `spec03-L2.11a.patch`. The audit and spec 03 patches are needed at merge (`test_audit_kinds` and `route-coverage-check`). `registry-L2.11a.patch` goes in with the merge.
11. **For ratification:** the routes in `app.py` (one block); the schemas commits 101d98c and 72f6a2d; the rows in `test_investigation_levels.py` and `test_route_rights.py`; `src/alerts/ruleStandards/**`; and Amendment 5 (written). **Still running:** nothing.

## Decisions taken (each the recommended option; the owner may overrule)

1. **Codec input.** Q: build on which rule model? Options: wait for L2.11's, or use today's `SentenceRuleInput`. **Chose:** `SentenceRuleInput`, one function per side, so the switch is one import. Agreed with rules.
2. **File shapes.** Q: how should DMN carry what FEEL cannot say? Options: FEEL expressions, or `osprey:` extensions. **Chose:** extensions, plus one fixed FEEL form per operator. Nothing is read as an expression (rule 8).
3. **Library.** Q: a BPMN/DMN library or hand-written XML? **Chose:** hand-written, read with `defusedxml`, which is already a dependency, so the licence register is unchanged.
4. **Import's right.** Q: `deploy_rules` or `author_rules`? **Chose:** `author_rules` at Author (the editor's draft right). Agreed with rules.
5. **Wiring.** Q: an `include_router` line or routes in `app.py`? **Chose:** three thin routes in `app.py`, the work in `rule_standards_routes.py`, as `watch_routes.py` does. Ratified by rules and the orchestrator.
6. **Import body.** Q: multipart or JSON? **Chose:** JSON (`RuleFilesUpload`), so the body is capped as it streams before anything is spooled.
7. **Declared dataset.** Q: membership of the read set, or the case's chosen dataset by kind? **Chose:** chosen and by kind (the strict option), refused as the app's missing dataset.
8. **Left as minor:** the fake store does not model another case's whole-deployment rule (a missing grant, not a refusal); `_attr`/`_text` are not `saxutils`.
9. **Left as minor:** XML-illegal control characters in a name would export a malformed file. The model allows them; the fix is a refusal at save, which belongs to rules' L2.11.
