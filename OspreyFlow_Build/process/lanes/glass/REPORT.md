# glass lane · report · L2.1 the alerts gap map

1. **Exit criteria.** All met. The map is at `spec/glass_redesign/ALERTS_GAP_MAP.md`. Every existing kind is in it with code evidence and the test that holds it (K1–K11, §2). The two new kinds are placed as not built (N1 drawn-item match, N2 promotions overdue, §3). Four questions are written as multiple choice (§6). `make citation-check product-tree-link-check` is green, with all 120 paths in the map checked; the map cites no `process/` file.
2. **Most important findings.**
   - G1: the queue and the Watches inbox are two lists of the same alerts.
   - G2 (rule 3, contradicted): the queue list checks an alert's nodes but not its cited links or transactions.
   - G3 (rule 3, untested): the inbox returns an alert's `words` whatever its evidence.
   - G6: "Alert goes to: my team" changes no one's view.
   - G7: there is no way back from the canvas to the alert.
3. **Commits.** fec0e07 is the map. The commit carrying this report and the friction fragment follows.
4. **Requests to the orchestrator.**
   - (a) Reserve the next ADR number, ADR-146 if still free, for "the alerts journey" (ADR-145 open question 1). I have not written it.
   - (b) Give G2 and G3 to the lane that owns `services/api/alert_queue.py` and `services/api/watch_routes.py`. They are rule-3 defects: write the failing test first, then fix. Neither file is the Glass lane's.
   - (c) Spec 02's "saved-pattern monitors… run on a schedule" is wrong: they run on the change stream (K10). This needs a spec fix by whichever lane owns `02_GLASS_FRONTEND.md`.
5. **Questions for the owner** (recommendation first; the full text is in §6 of the map).
   - **Q1, one list or two.**
     - A: one queue, with ADR-130's explanation for every kind; the notices go to Home; the jump becomes a view.
     - B: keep both and rename the inbox.
     - C: as today.
   - **Q2, where the new kinds live.**
     - A: the drawn-item match is a medium typology alert in the case queue, with *Open the board*; promotions overdue goes to *Needs you* and Admin › Operations, for `review_promotions` holders and administrators.
     - B: both in the case queue.
     - C: a fourth queue kind, *board*.
   - **Q3, what "my team" means.**
     - A: a label plus queue filters (mine, team, unassigned, older than N days).
     - B: only the author's unit sees the alert.
     - C: remove the choice.
   - **Q4, alert to case and back.**
     - A: open the alert as a private view, with "← Back to the alert" in the context banner; Home's rows open the alert.
     - B: only Home's rows open the alert.
     - C: as today.
6. **Hand check (G1, the biggest gap).** Do this in Operation Ledger after `DEMO_GUIDE.md` §8b step 1, once the hotlist on `GB58 LOYD 3096 1700 7099 43` exists.
   - From `OspreyFlow_Core`, run `.venv/bin/ospreyflow start`.
   - Then run `PYTHONPATH=.:packages .venv/bin/python -m scripts.seed_internal ledger --release-week-2` and run the week's pipeline in the Studio, as §8b says.
   - In the Glass, open *Monitoring → Queue* and open H1: it names no identifier, file or row.
   - Then open *Monitoring → Watches*: the same alert, in the inbox, says "Hotlist: GB58…", the file and the row.
   - Press *Show on the canvas*, then try to get back to H1: only the rail's *Monitoring* entry leads back, and the alert is closed again.
7. **What is left.** The ADR, after the owner's answers. Nothing else in L2.1.
8. **Still running.** Nothing. The two read-only research agents have finished. No dev stack and no lease were used.
