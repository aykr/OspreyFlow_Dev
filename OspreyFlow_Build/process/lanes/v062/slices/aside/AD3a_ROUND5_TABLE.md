# AD3a, round 5: every open case (the conductor, 25 November 2026, 06:24 UTC)

The demo server's run `831b70ddc4a1a396` was red for AD3a at `88f1896646` on one test, and the line's
`server-rerun` found it red on the Mac too; the conductor ran it on main (green, 1 passed) and on AD3a's tip (red).
**One open case; this round is that row and nothing else.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **`OspreyFlow_Build/tests/glass_trees/test_studio_frame_scenarios.py::test_the_words_gate_finds_target_model_in_the_scenarios` fails on your tip and passes on main.** It takes the real `spec/08_ACCEPTANCE_SCENARIOS.md` (through `planted()`), appends the line `Edit target model`, and asserts the Studio words gate (`problems(...)`) reports "target model". After your 30 added lines in spec/08, the appended line is no longer found: most likely your new section is where the appended text lands, and the gate does not read that section (or your section's shape ends the scenario rows the gate reads). | your spec/08 addition; the gate's reader only if it is wrong | Find which: read how `problems` finds the scenario rows it checks, and why the appended line falls outside them with your section present. **Fix your spec/08 section so the gate reads the document as before** (its heading, place or row shape), not the test and not the gate, unless the gate itself is wrong, in which case say why in your report and stop before changing it (it is the Studio's words gate, not this part's). Run that test file and `test_ui_words_check.py` before you stop. |
