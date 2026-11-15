# v0.6.0 #6: GOV.UK type — the mono words, then one confirming pass

The owner's closed list asks for two things: fix the words set in mono, then make one confirming pass over every
screen in the GOV.UK look. The orchestrator triaged what the pass found, and ruled again after the lane review
(15 November 2026). The branch is rebased on main 582bab2.

## 1. The mono words (Admin)

Several Admin labels were set in mono:
- a role's label, and a custom role's name;
- a schedule's label;
- the tips' role labels, and "Levels in a case";
- an organisation arrival's sign-in name.

They are now in the page's face (`.admin-words`). Mono is kept for values to copy.
- `keyboard/admin-words-face.spec.ts` measures the computed face in every look.
- `red_mono_words.log`: 9 failed before the fix.
- `plants_mono.py` and `plants_mono.log`: 6 plants, each red where it must be, at dd5ff55.

## 2. The confirming pass, and its list

`keyboard/govuk-type-pass.spec.ts` walks every harness page that applies the brand: 44 pages, in each of every-harness's
states (269 page-states). It measures every visible element that has text of its own, under `brand=govuk`:
- **Face:** mono only on a value to copy.
- **Size:** on the scale where the element sits, read from its own `--fs-*` tokens.

`CONFIRMING_PASS_LIST.md` is the list sent before any fix. It holds 415 findings in seven causes, A to F, with the
raw findings in `govuk_pass.jsonl`. Its counts were corrected in place on 15 November. The orchestrator ruled:
- **A and C, in both looks:** bare headings and controls go on the one scale. h5/h6 were added unasked (a346002) and
  then ruled kept, as the same defect.
- **F kept:** GOV.UK Frontend's own classes keep GOV.UK's sizes, so the pass does not read their size, though it
  reads their face.
- **B, D1 and D2 in scope.**
- **E left out:** the harness's own chrome is marked `data-harness-only`.
- **(b), after the lane review:** read the names the pass cannot see, because it trusts `.value`. See section 4.

## 3. The fixes

- **A and C** (`src/design/scale.css`, which primitives.css imports before panelType.css):
  - zero-specificity sizes for bare headings: `h1` `--fs-23`, `h2` `--fs-19`, `h3`/`h4` `--fs-16`, `h5`/`h6` `--fs-12`;
  - `font: inherit` on buttons, inputs, selects and textareas.

  A component's own size wins, and so does a panel's own label rule, which comes later and so wins a tie of
  `:where()`. The whole keyboard suite once caught that order the wrong way round (see `keyboard.log`). The rule is
  in DESIGN.md §2, in both copies.
- **B:** the Ingest Studio's `0.8em`, `0.85em` and `1.1em` become `--fs-11` and `--fs-14`, with their line heights.
  This covers Profile, Test, Load rules, Deploy and Map, including the Map editor's pattern-match chip.
- **D1:** the home glyphs (△, ·) and the selection bar's reading ("direct", "within 2") are in the page's face.
- **D2:** values are classed `.value`, and the duplicate inline mono beside them is removed. This covers the Studio's
  sample cells, a check row's sample (its "row 4:" now in the page's face) and the SQL and YAML editors.

## 4. Names wrongly classed `.value` (ruling (b))

The pass trusts `.value`, so a name classed as a value is invisible to it. Each site was read and called:

| Site | What it shows | Call |
|---|---|---|
| `help/RolesHelpPage.tsx` (dt ×4) | a place's, a role's, a level's name | name: page's face |
| `ingest/checks/ChecksScreen.tsx` | a load rule's name | name |
| `reports/DataFeedsTab.tsx` | a data feed's label | name |
| `matrix/MatrixView.tsx` | an entity's name, a row's header | name (the Inspector sets an entity's name in the page's face) |
| `reports/PackItemView.tsx` | an entity's name in a pack | name |
| `questions/QuestionsPanel.tsx` (source) | a source's name | name |
| `questions/QuestionsPanel.tsx` (candidate) | a proposed entity's type and name | name (found beside the above) |
| `alerts/RuleEditor.tsx` | a dataset's name | name |
| `inspector/SelectionList.tsx` | a selected entity's name | name (found in the same survey) |
| `home/HomePage.tsx` (service) | a service's name | name (as Admin › System's part names already are) |
| `home/HomePage.tsx` (signed in as) | a username | **value**: an identifier, kept in mono |

`src/design/namesNotValues.test.ts` checks each site at its own source. `red_names.log`: against main's code, all
12 name cases fail, and the username case passes.

## 5. The gate (rule 15)

The pass is now a gate in the keyboard suite: any finding fails its page. `GOVUK_PASS_LIST=1` lists without failing.
- **Guard:**
  - It takes every-harness's `EXTRA_STATES` by evaluating its literal, so no state is filtered out.
  - It counts the states again from the source's string literals.
  - It asserts that the look it claims was drawn, and that something was measured.
- `plants_gate.py` and `plants_gate.log`: 3 plants, each red at its named assertion.
  - The first draft's filter: 253 states, not 260.
  - The brand never applied.
  - Nothing measured.
- `gate_red.log`: against main 582bab2's code, with only the test side copied in, **94 of 270 tests fail**, with 382
  findings.
- `gate_green.log`: at ba4bf1c, every page-state passes, with 0 findings.
- `standard_look.md`: the standard look, with no brand. Before (main's code) it has 464 findings, raw in
  `standard_before.jsonl`. After (ba4bf1c) it has 0. Every element and size is listed with its pages.

## 6. Suites (local slot 5, the orchestrator's)

- `keyboard.log`: the whole keyboard suite at ba4bf1c, 1352 passed and 5 skipped.
- `a11y.log`: the whole a11y suite at ba4bf1c, 1166 passed. every-harness runs in it in the dark, light and GOV.UK
  looks.
- `make -k ci`: on the server, in the queue.

## What the gate does not see

- **Words classed `.value`.** It trusts the class; section 4's check holds the names found.
- **Text the gate does not read.** It reads elements with text of their own, so a field's typed value, a select's
  shown option and a placeholder are not measured.
- **Whether a size suits its role.** It asks only whether a size is on the scale, not whether the size fits the
  element's role. For instance, a label heading at 19px sits on the scale; glass-panels-look is what caught that.
- **23 harness pages that do not apply the brand.** Examples are welcome, reports, packs, trends, publish,
  pipeline-studio and connections. They are walked in neither look, though scale.css applies to them too. Their bare
  headings now take the scale's sizes in the standard look, unmeasured.
- **Screens with no harness, and the live Glass.** The harnesses import the same tokens.css, primitives.css and
  component CSS as `main.tsx`.
- **Content that renders after a fixed 400ms wait.** The page waits for network idle and fonts, but anything that
  appears later is not measured.
