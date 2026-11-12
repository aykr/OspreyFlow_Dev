# Platform lane · brief R1 · the client install's acceptance on kind (L)

Written by the orchestrator, 12 November 2026, at the owner's order, for a **fresh platform session on `sol`**, from
**main** (`git fetch`, branch `lane/platform-r1` from `main`). Read P7b's install runbook and decommission runbook as
rendered (harness/cloud_platform/runbooks.py → INSTALL.md, DECOMMISSION.md), ADR-148 Amendments 5 to 8, P9's
RUNBOOK.md (backups and restore) and the guide's §6a first. Opus, medium. Size L.

**The owner's words:** R1 is the client install's acceptance. The `cloud-platform` profile in `shape: poc`, installed
on kind by following P7b's install runbook **exactly as written**, checked, backed up and restored, then removed by
the decommission runbook. Every place the runbook is wrong or unclear is a finding: fix the runbook and the product,
then run the affected part again. Say what a platform team member would have been stuck on. **The v0.5.1 release is
cut from the commit that passes R1.**

**Timing.**
- **Until Friday evening: no server.** Prepare on the Mac: read both runbooks as a platform team member would; list
  every command and what it needs; prepare the kind cluster's settings; write the check list (what "checked" means:
  sign-in, a case, a load, a rule, a backup set, a restore beside a live store, the decommission's leftovers).
- **Nothing on the server from 12:00 UK on Friday 13 November** (the owner's demo) until the orchestrator says the
  demo is over.
- **From Friday evening, on the orchestrator's word:** run it. The lanes' heavy runs are paused while R1 has the server.

**Memory (the owner's decision, 12 Nov): osprey-small stays up.** After the demo, the demo lane caps osprey-small's
sizing (server.memory_gib 62 → about 24, one apply), and its local model unloads when idle. Your kind node gets
**about 30–32 GiB** (the poc development shape asks about 27 GiB, limits about 33). The 10 November attempt ran out
at a 4 GB node. Record the node's memory and every pod's actual use in your record. Disk (~30–40 GB of 572 free) and
CPU (~4 of 16 cores) are not constraints.

**Records:** each runbook block as run (copied from the rendered runbook, the placeholders filled as an operator
would), its output, and each finding with its fix and the re-run. A plain-words list for the owner: where a platform
team member would have been stuck. Gates at the final head as every step.

**Never.** osprey-small is the demo lane's, never yours: no command touches its containers or volumes. No push. No
real data. Nothing reachable from the internet.
