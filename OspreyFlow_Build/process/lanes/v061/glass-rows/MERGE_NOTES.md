# The Glass rows: merge notes (after v0.6.0's release)

Order: case's B (lane/case-v061-glass-rows-build, 36e05c8), then case-b's A+C (lane/case-b-v061-glass-rows-ac, 30edfaf, on 739ffd1).

At B's merge:
- apply case's process/lanes/case/glass-rows/registry-glass-rows.patch and every-harness-glass-rows.diff;
- B removes views/ViewLensBanner.tsx: OWNER_BRIEF_2026-11-16.md:23 cites it, so citation-check fails; mark the brief's cell as the file then current (a dated note) or allowlist it;
- the guide 1.73 history row: set the version line, reprint the PDF, restore the other guides' PDFs and manifest entries; run every test_user_guide*.py.

At A+C's merge:
- apply case-b's process/lanes/case-b/v061-glass-rows-ac/registry.patch (three CANVAS_ACTIONS ids);
- the user guide's version bump and PDF reprint (§5.2 "Hiding the toolbar", Match strictness);
- the whole keyboard suite and every-harness on the merged tree; whole vitest;
- v0.6.1 list: T on the map's container (platform).
