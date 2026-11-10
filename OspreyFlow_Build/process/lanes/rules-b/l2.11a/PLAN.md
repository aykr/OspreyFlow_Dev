# rules-b · L2.11a · plan (10 November 2026)

Working from ADR-146 decision 3 ("Stored to the standards") and its tests; rules 1, 3, 4, 7, 12, 13, 15.
Interface agreed with rules by message (10 November; five changes taken: osprey:dataset carried; unknown
osprey:* elements and attributes refused too; import checks the declared dataset, a dataset outside the
case refused as a missing one; an upload cap before parsing; focus back to the button on close).

**Tests first** (each shown red by a plant at the real call site, RED_RECORD.md):
1. `OspreyFlow_Build/tests/rule_standards/test_codec.py`: every sentence shape (each condition op, each
   relationship, frequency and strength kind, schedule, Then) exports and imports to the same rule; a real
   exported file plus a `bpmn:exclusiveGateway` is refused naming it; the same for a DMN element, an unknown
   `osprey:` element and attribute; a file with no dataset refused in words; DTDs and entities refused.
2. `OspreyFlow_Build/tests/services/api/test_rule_standards_routes.py`: export needs the right, the place and
   the case; another case's rule is the same 404 as a missing one; a rule with no dataset is refused in words;
   import needs the Author level and `deploy_rules`, refuses a dataset outside the case as a missing one,
   refuses over the cap before parsing, checks names against the model, writes nothing.
3. `test_route_rights.py`: three rows.
4. `apps/workspace/src/alerts/ruleStandards/ShowAsBpmn.test.tsx`; `keyboard/rule-standards.spec.ts` with its
   harness (opens by Enter, Escape closes, focus back on the button); axe in dark, light and GOV.UK.

**Files:** `OspreyFlow_Core/packages/rule_standards/{__init__,codec}.py` (new);
`OspreyFlow_Core/services/api/rule_standards_routes.py` (new) and its `include_router` line in `app.py`
(ratified by rules); `apps/workspace/src/alerts/ruleStandards/**` (new, by rules' agreement); keyboard
spec, harness and the a11y harness by diff; `registry` diff as a patch.
