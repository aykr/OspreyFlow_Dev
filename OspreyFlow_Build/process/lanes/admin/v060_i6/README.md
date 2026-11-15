# v0.6.0 #6: GOV.UK type — the mono words, then one confirming pass

The owner's closed list asks for the words set in mono to be fixed, then for one confirming pass over every screen in
the GOV.UK look. The orchestrator triaged what the pass found (15 November 2026).

## 1. The mono words (Admin)

Commits bc4ac31 (red first) and 491c104 (the fix). A role's label, a custom role's name, a schedule's label, the tips'
role labels and "Levels in a case", and an organisation arrival's sign-in name were all set in mono. They are now in
the page's face (`.admin-words`). Mono is kept for values to copy.
- `keyboard/admin-words-face.spec.ts` measures the computed face in every look.
- `red_mono_words.log`: 9 failed before the fix.
- `plants_mono.py`: 6 plants, all red.

## 2. The confirming pass, and its list

`keyboard/govuk-type-pass.spec.ts` walks every harness page that applies the brand, in each of every-harness's states,
under `brand=govuk`. It measures every visible text element:
- **Face:** mono only on a value to copy.
- **Size:** on the scale where the element sits, read from its own `--fs-*` tokens.

`CONFIRMING_PASS_LIST.md` is the list sent before any fix: 415 findings in seven causes, A to F, with
`govuk_pass.jsonl` as the raw findings. The orchestrator ruled:
- **A and C, in both looks:** bare headings and controls go on the one scale.
- **F kept:** GOV.UK Frontend's own classes stay at GOV.UK's sizes, and the pass leaves out `govuk-*`.
- **B, D1 and D2 in scope.**
- **E left out:** the harness's own chrome is marked `data-harness-only`.

## 3. The fixes

- **A and C** (`src/design/scale.css`, imported by primitives.css before panelType.css):
  - zero-specificity heading sizes: `h1` `--fs-23`, `h2` `--fs-19`, `h3`/`h4` `--fs-16`, `h5`/`h6` `--fs-12`;
  - `font: inherit` on buttons, inputs, selects and textareas.

  A component's own size wins. A panel's own label rule wins too, because it comes later; the whole keyboard suite
  caught that order once, see `keyboard.log`. The rule is in DESIGN.md §2, both copies.
- **B:** the Ingest Studio's `0.85em` and `1.1em` become `--fs-11` and `--fs-14`, with their line heights (Profile,
  Test, Load rules, Deploy, Map).
- **D1:** the home glyphs (△, ·) and the selection bar's reading ("direct", "within 2") are in the page's face.
- **D2:** values are classed `.value`: the Studio's sample cells, a check row's sample (its "row 4:" in the page's
  face), and the SQL and YAML editors.

## 4. The gate (rule 15)

The pass is now a gate in the keyboard suite: any finding fails its page. `GOVUK_PASS_LIST=1` lists without failing.
- `gate_red.log`, at 376c52b (the gate and the harness marks, before the fixes): **87 of 260 pages fail**, with 365
  findings, and none of them from the left-out GOV.UK classes or harness chrome.
- `gate_green.log`, at c226c80: **260 of 260 pass**, with 0 findings. The pass passes again in the whole keyboard
  suite at 9db7d73.
- `standard_look.md`, the standard look with no brand: 435 findings before, 0 after, each element and size listed.

## 5. Suites (local slot 5, the orchestrator's)

- `keyboard.log`: the whole keyboard suite at 9db7d73: 1338 passed, 5 skipped.
- `a11y.log`: the whole a11y suite (every-harness in the dark, light and GOV.UK looks, and the others) at 9db7d73.
- `make -k ci`: on the server, in the queue (third).

## Not measured

The live Glass on a deployment. The harnesses import the same tokens.css, primitives.css and component CSS as
`main.tsx`, so what they measure is what the Glass draws. A screen with no harness is not walked.
