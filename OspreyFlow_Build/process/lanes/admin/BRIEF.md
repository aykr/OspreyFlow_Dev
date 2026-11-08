# Admin lane · brief L2.5 · people and roles, custom roles, teams and leads, and Disable

Written by the orchestrator, 8 November 2026, after L2.4 part 2's merge. Rebase onto `main` first. Opus,
medium. Size L. **Split** (the orchestrator's judgement): *Disable…*'s full transfer list reads the case
lane's ownership route (L3.8), several case steps away (merge order 6). So L2.5 builds everything below and
*Disable…* for what a person can own today; **L2.5b** (S) completes the transfer list once L3.8 is on main.

**The lane.** `lane/admin` owns `apps/workspace/src/admin/**` except the Models and Maps sections, and the
Admin, people, roles, teams and audit routes in `services/api`. The shell, Home and the GOV.UK header are
the rules lane's. Live runs take a test stack (`stack_lease.sh acquire admin "<purpose>"`, a or b; pin
the ports it prints). Before ready-to-merge: your own lane-reviewer pass, then make ci and make test at a
commit (Prompt L).

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 12, 13 and 15 above all); ADR-145 decision 7 and
Amendment 4 (R1, R2, R3, A4, the guard rails); ADR-112 and Amendments 4, 5 and 7 (rights; the *Rule
author* role and the Super user preset; `author_rules`, `merge_datasets`; a service account owns
nothing); ADR-146 and Amendment 1 (teams, the lead, hand-over and cover, as the queue will read them);
`spec/02_GLASS_FRONTEND.md`'s Admin area and `spec/03`'s people routes.

**Build** (the plan's row L2.5):
1. **People:** the row (R3); Author visibility and *Name an Author* (R1).
2. **Custom roles** (R2): an administrator defines a role from rights, with ADR-145 decision 7's
   refusals at the route (the guard rails: no role that would lock every administrator out, no right a
   role may not hold, service accounts refused).
3. **ADR-112 Amendment 5:** `author_rules` and `merge_datasets` as rights, the *Rule author* role and the
   Super user preset. Rights changes go to the orchestrator as a small `packages/schemas` commit, merged
   first; run the whole of make ci on it before sending.
4. **Teams:** name, mailbox, a level in a case, ownership; **the lead**, hand-over and cover, in the shape
   ADR-146 Amendment 1's queue tools will read (rules' L2.10 consumes it; say what you expose).
5. ***Disable…*** with transfers for what a person can own today: cases (and their home cases), datasets'
   Authors, and anything else on main that names an owner; refused, in words, while any item is
   untransferred. Leave one clearly named seam for L3.8's ownership route (views, boards, promotions,
   proposed types) and list it as L2.5b's.

**Tests first, each red by a plant at the real call site:** decision 7's refusals at the route, each red
with its check removed; *Disable…* refused with an item untransferred, and allowed once all are; a
service account can neither own nor be made an owner or lead; a custom role's rights are exactly what it
was given (red with one extra); ADR-112 Amendment 5's tests; keyboard cases for every new action (rule
13), their registry ids as a diff for the orchestrator; axe in dark, light and GOV.UK.

**Carried from L2.4 part 2's review, fix if quick:** a deployment default for the promotion policy; the
policy shown under Details rather than in the row; registry ids for Details and Cancel.

**Exit.** The row's exit except the L3.8 seam; make ci and make test green offline; the live cases under a
named lease and stack; a friction fragment. Report in Prompt L's format, then stop.
