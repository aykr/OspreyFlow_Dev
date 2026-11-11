# docs lane · handoff at the pause (11 November 2026, before 07:15)

`lane/docs` = main `ac8735d` plus this file (and, if listed below, the report). Nothing is running; no stack is held.
The decks are outside the product repo, in `OspreyFlow_presentations/` (git-excluded), so they are not in any commit.

## First, on resume: the rule editor in the guides (the orchestrator's order)

The published guides describe the rule editor as built but do not yet explain it. Write, from main's code and ADR-146
Amendment 6 (facts already gathered in `OspreyFlow_presentations/D2B/CLAIMS.md`, section "The rule editor"):
- **User guide §7** (Monitoring and alerts): §7.1 the place's four tabs (Alerts, What raises alerts, Held rows for an Editor
  or Author, Changes for an Author or administrator); §7.4 and §7.6 rewritten around **Write a rule on a dataset**: the
  dataset chosen once, the sentence, severity, *For* this case, *Alert goes to*, *Runs* (after/before commit, schedule,
  list refresh), *Show the drawn pattern*, *Preview on the last 90 days*, **Save the draft**, **Test on the last 30 days**,
  **Make live** (needs `deploy_rules`; a Rule author alone cannot), the second person by the dataset's
  `promotion_policy`; *Open in the rule editor*; Versions, *Schedule and runs*, the Changes tab; **Show as BPMN**
  (read-only; export and import are API routes only). The older forms keep a rule "just for me" (`use_the_rule_editor`).
- **Administration guide §9.4–9.6**: who writes and makes rules live (rights by role, from `packages/schemas/rights.py`),
  no whole-deployment rule, `migrate_rules_to_datasets`, a rule running as its author who must still hold `author_rules`
  or `deploy_rules` (decision 13), assigning Rule author after the update, the second person.
- MORNING items 13 and 17's decisions as built (all built; item 17(a)'s template-to-draft path is *coming*).
- Version rows (user 1.44, administration 1.70 or the next free), `make docs-pdf`, the docs tests and gates, a friction
  row; send "built at <hash>" for the independent review.
- A note to the orchestrator already sent: CHANGELOG.md:135's "export or show as BPMN" is true for export only through
  the API; its v0.5.0 section is the orchestrator's.

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
