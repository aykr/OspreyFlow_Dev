# Admin lane · brief L2.5b · Disable's full transfer list

Written by the orchestrator, 10 November 2026, for a **fresh admin session** (`ayan`), **started from lane/admin at
ffd5ee2 (L2.7, merging now)**: build on it, and rebase onto main once L2.7 is merged (the orchestrator tells you).
Read ADR-145 Amendments 5 and 8 (Amendment 8 is the owner's Disable ruling) and case-b's L3.8 REPORT first. Opus,
medium. Size S.

**The lane, the stacks, the merge rule.** Test stacks are on the owner's server only (b to g); Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator for a stack, then main's `stack_lease.sh` (acquire, up, `remote admin -- …`, down, release; `remote-log admin` reattaches). `make test` runs on the server: `stack_lease.sh offline admin -- sh -c 'make -k test SKIP_JS=1; cd ../OspreyFlow_Core && make test-js'`. Ask before `make -k ci` or any Playwright here (two heavy runs at most). Never call remote or offline while one of your runs is alive. Prompt L's rules: never stop on a question; build the recommended option (the strict one for access) and log it under "Decisions taken"; real data stops a piece. Your own lane-reviewer, then the gates at a commit rebased onto main, saved under `gates/`, with one leased live run including `test_route_rights.py`; re-gate after any code change. Report to the orchestrator **by message**.

**Build** (CARRIES' L2.5b row and ADR-144 decision 6's count): People's *Disable…* reads L3.8's ownership route and
offers each item's transfer; `refuse_if_withheld` called after the visible transfers commit (409 withheld_items,
naming nothing); OwnedKind gains view, board, link_type_proposal and drawn_watch; `l38_owned_items` takes the
administrator's unit and the scheme (`reach`); `_TRANSFER_SQL` and NEEDS (draw_on_boards, propose_types) for the four
kinds; remove the ownership route's line from `test_admin_sections.py`'s NOT_A_SECTION_S; *Admin › System*'s count
of cases converted to views. Also from your L2.7 review: Admin's dry run of a removed case's layer limited to the
dataset's own unit (the owner's ruling (a) on L3.4). The Author-transfer route (Amendment 8 decision 4) is in scope if
small; otherwise name it as left. Tests first, red at the real call site; keyboard (rule 13) and axe.

**Exit.** Disable completes for a person whose items are all visible, and is refused in words while any is withheld; a
friction row.
