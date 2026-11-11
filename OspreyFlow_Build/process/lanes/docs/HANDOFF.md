# docs lane · handoff at the pause (11 November 2026, before 07:15)

`lane/docs` = main `ac8735d` plus this file (and, if listed below, the report). Nothing is running; no stack is held.
The decks are outside the product repo, in `OspreyFlow_presentations/` (git-excluded), so they are not in any commit.

## First, on resume: the rule editor's guide step (built at 3b602a5, waiting for review)

User guide 1.44 §7.1–7.6 (and §7.11–7.12 where they contradicted it) and administration guide 1.70 §9.4–9.6, with spec 10's
mirror, describe rules' L2.10 and L2.11 as built, from main's code and ADR-146 Amendment 6 (MORNING items 13 and 17's
decisions included; 17(a)'s template-to-draft path is *coming*). PDFs reprinted (user and administration; the developer and
architecture PDFs kept, their sources unchanged); the docs tests (182) and gates green; friction row
`2026-11-11-docs-rule-editor-guides.md`. Sent to the orchestrator as "built at 3b602a5".
- On resume: fix both reviews' findings together, rebase onto main, then gate once on the server
  (`stack_lease.sh offline docs -- sh -c 'make -k ci'` and `make test`), and send ready-to-merge with the head from git.
- Captures this step needs (default and GOV.UK): `images/user/09-monitoring.png` (the queue's filters, What fired it),
  `13-watches.png` (its subject, the Watches tab, is gone: What raises alerts' hotlists and patterns instead),
  `22-rule-sentences.png` (the rule editor: dataset, draft, Test, Make live).
- Told the orchestrator: CHANGELOG.md:135's "export or show as BPMN" is true for export only through the API (its v0.5.0
  section is the orchestrator's).

## Then: D2b, the decks

State at the pause, every draft new beside the old (the owner approves each before it is shown outside):
- `OspreyFlow_Product_Overview_Draft1m.pptx`, `OspreyFlow_Administration_Architecture_Draft4.pptx`,
  `OspreyFlow_AML_Opportunity_Draft3.pptx`, `OspreyFlow_Pitch_Deck_Draft3c.pptx`, `OspreyFlow_AE_Enablement_Draft2.pptx`
  (each built by `D2B/edit_<deck>.py` from the previous draft), and the three Prison Intelligence decks `*_rev5.pptx`
  (built by `prison_intelligence_demo/decks/build_decks.py`; rev4's script kept as `build_decks.rev4.py`), with
  `PRISON_DEMO_SCRIPT_v5.3.md`, `PID_DEMO_SETUP_GUIDE.2026-11-10.md` and `HMP_Prison_Network_Demo_Script_v2.md`.
- `D2B/CLAIMS.md` is what the decks may say (corrected after the independent review); `D2B/CHANGES_<deck>.md` records each
  slide's change and its CLAIMS line; `D2B/CAPTURES.md` lists every capture; `D2B/pptx_tools.py` is the stale check, with
  its planted cases in `D2B/test_pptx_tools.py` (shown red by removing a pattern).
- The independent review's fixes 1–14 are all made (11 November, 05:41), and the rule-editor placeholders are filled from
  CLAIMS' rule-editor section (PO 32, AML 36, prison 34 / 23 / 28); each deck rebuilt once from its script. The stale check
  (`D2B/pptx_tools.py`, its plants passing) reports 0 for all eight decks and the HMP run-sheet; `PRISON_DEMO_SCRIPT_v5.3.md`
  (5) and `PID_DEMO_SETUP_GUIDE.2026-11-10.md` (4) hold only reviewed false matches (prose saying there are no branches, a
  pipeline's branch), listed in `CHANGES_prison.md`. Sent as "built" for the orchestrator's second review.
- Still to do: the owner's approval of each draft; the open owner questions in each `CHANGES_<deck>.md` and v5.3's Appendix E
  (item 8: no Delete for a board was found on main, so how rehearsal boards are removed); fit is judged by text length only
  (no renderer): AE slide 11 and the prison rule-editor slide's subtitle are the tightest.
- **After v0.5.0 is published:** the Pitch's slide 25 headline ("v0.4.12 released") and reference [10] (v0.4.12's tag) move
  to v0.5.0, its link checked (a HEAD request; the tag answered 404 at 05:35).
- **Captures:** a full recapture from the server's demo deployment after the release (the orchestrator's decision).

## Rules for whoever resumes

- **No desktop apps** (Keynote, PowerPoint, Preview, `qlmanage`, `open`, `osascript`): python-pptx and text only.
- **Files outside the worktree** (`OspreyFlow_presentations/`): read them with Bash, not the Read tool. A Read there raised a
  permission prompt at 18:13 on 10 November and froze this lane until about 05:40 (MORNING item 30).
- Heavy runs (`make -k ci`, `make test`) on the server through `stack_lease.sh offline docs`; Playwright needs a Mac slot
  and, after T2, `OSPREY_PORTS_SLOT=4`.
