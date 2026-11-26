# GG2a, round 4: a GPU switch for the Mac's measurement (the conductor, 26 November 2026; the owner's question 4, (a))

From the verified tip `313b742`. The perf runner (`OspreyFlow_Core/apps/pages/test/perf/`) launches Chromium as CI does,
with software WebGL, so a figure taken on the Mac today measures the software renderer, not the Mac. **This round is the
row below and nothing else. CI's gate, its thresholds and its default launch stay as they are.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | An opt-in switch, `PAGES_PERF_GPU=1`, read by `playwright.config.ts`: with it, Chromium launches with the GPU (no software WebGL flags; say which launch options you chose and why). In every run, switched or not, `graph.spec.ts` reads the WebGL renderer string once (`WEBGL_debug_renderer_info`'s `UNMASKED_RENDERER_WEBGL`, or `RENDERER` where that extension is absent; say which) and `record()` writes it into every figure as `webglRenderer`. **Under the switch, a software renderer (SwiftShader, llvmpipe, "Software", or no WebGL context at all) fails the run before any figure is recorded, with the renderer string in the message.** Red first (rule 15), at the shape the code really sees: a test of the refusal fed the renderer strings Chromium really reports for SwiftShader (from a software run, quoted in your report) must fail with the refusal removed and pass with it. Then a GPU name must pass. | Your frozen checks green. A software run (`npm run test:perf --workspace apps/pages`, no switch) records `webglRenderer` on each figure; with `PAGES_PERF_GPU=1` in your worktree it either records a GPU renderer or refuses with the renderer string (your sandbox may hide the GPU: either line is the record, and neither is a measurement of the Mac). Report both lines. **The default launch and every gate figure unchanged:** `git diff 313b742` shows no change to `FIRST_FRAME_GATE_MS`, `SWEEP_GATE_MS` or the default launch options. Then write the exact command the owner runs on the Mac (the switch, `PAGES_PERF_RECORD=<file>`, three runs) into the slice's report. |

**Added 26 November 2026, 12:25 UTC (the conductor), after the owner's Mac run and ruling:** the owner measured on the
Mac (`~/gg2a-mac-gpu.jsonl`, 3 runs, Apple M3 Pro GPU, all passed: first frame 2,877 / 2,646 / 2,954 ms; sweep 16.5 /
17.0 / 16.5 ms a frame; expansion of 500 nodes 555 / 602 / 684 ms against the Mac's 800) and ruled: **carry on with
Sigma 4, no fallback.** Copy those figures into the away report's round-4 section as the owner's. **Rows 2 and 3 below are not this round's:** I20 (`same_drawing_versions_check.mjs`, its tests) is not on main; it arrives
with WS4a. They come in a later round, after WS4a merges. **This round: copy the figures, merge nothing else, and rerun
your checks.**

| # | Do (a later round, after WS4a merges) | Done when |
| --- | --- | --- |
| 2 | **The version-window entry (WS4a Q1 (a)):** `apps/pages/VERSION_WINDOW.yaml` gains the `sigma` entry (workspace 3.0.3, pages 4.0.6, the day the window opens), so the branch's lockfile passes I20. WS4b removes it. | I20 green with the entry, red without. |
| 3 | **I20's third test (WS4a Q5):** `test_no_sigma_page_merges_in_the_window.py` as WS4a's report describes it, red first at the real shape, then green. | Red with its plant, green on the branch. |
