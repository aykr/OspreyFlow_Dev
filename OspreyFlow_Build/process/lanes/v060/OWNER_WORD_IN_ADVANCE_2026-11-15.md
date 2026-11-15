# v0.6.0: the owner's word in advance for stages 3, 4 and 5 and the demo rebuild

From the owner, 15 November 2026 (~18:10Z), beside the plan of record (`OWNER_PLAN_2026-11-15.md`). Recorded by the
orchestrator; the owner's own wording, condensed only where marked.

Start each stage as soon as the one before it finishes, at any hour. The dates in `route.tsv` are the latest, not the
earliest.

## 1. Approved in advance

| Step | The owner's word | Only if |
|---|---|---|
| Stage 3: the candidate | Make it and merge it | Every item on the closed list is merged on main and nothing outside the list has joined. CI is green on the exact commit the candidate is made from. Stage 2's leak test, never-join check and timings passed, no figure waived. |
| Stage 4: the package test | Start it straight after the candidate | The candidate is the commit CI was green on. |
| Stage 5: the release | Release v0.6.0 | The package test passed on the candidate with every check; none waived or skipped, and none re-run to green without the reason written down. The release is made from the same commit the package test ran on. |
| The demo rebuild | Rebuild the GOV.UK demo from v0.6.0 straight after the release, at any hour, from `demo/REBUILD_2026-11-18.md` | The backup at step 1 is taken and its restore dry run passes. The old folder is kept as the way back. No visitor has a sign-in yet, so the downtime needs no notice. |

This replaces the fixed window of Wednesday 18 November 07:00 UK: the window is now "as soon as the release is made".

## 2. What stops the run and comes back to the owner

Stop at the step, leave everything as it is, and write what happened at the top of `MORNING.md`, if:

1. A condition in the table does not hold.
2. A check fails and the fix is anything other than re-running a step that failed for a recorded reason outside the
   product (the server, the network, a queue).
3. Any change to `OspreyFlow_Core/Makefile` or `.github/workflows/ci.yml` is needed (they come to the owner as diffs).
4. Any part of the release would make something public or reachable from the internet that is not already: a public
   repository, a public registry, the reserved name, either website. Do the private parts, stop at that part, and say
   exactly what would be pushed and where.
5. A ruling would remove or defer something the client page or an ADR requires.
6. The rebuild's way back (the restore into the old folder) is used.

## 3. Not covered (still the owner's word)

Anything public (the two websites, DNS, a public repository, claiming the reserved name); visitor sign-ins (the
proposal first; no visitor holds Admin); anything on the v0.6.1 list, the Admin forms branch included; real data of any
kind.

## 4. Gemini's key on the rebuilt demo

1. Do not wait for the owner: run the rebuild to the end without the key, the demo on its own model, Gemini declared
   with no key, every check that needs no Gemini run; the Gemini checks (the engine choice, one answered question, the
   1,000,000 tokens a day budget, the datasets' egress) recorded "waiting for the owner's key".
2. At a terminal the owner runs `ospreyflow models key gemini` at the hidden prompt; then the Gemini checks run. The
   exact command, ready to paste, goes in `MORNING.md`.
3. Answered before the rebuild: can the key held encrypted in osprey-small's gateway database be carried into the new
   deployment without retyping? Only if: it is never decrypted outside the gateway, printed, written to a file, log,
   message or the repository, or read by anyone; what moves is the gateway's own encrypted record with the encryption
   key it needs, server to server, both already covered by the backup; it is rehearsed first on the test stand-in with a
   synthetic key, showing the carried key answers a call and appears in no file or log; and the new deployment's records
   say truthfully how the key arrived (carried, by whom, when). If any cannot be met, or the rehearsal takes more than
   about an hour of a lane's time, say so and leave it: the owner types the key. No new product feature for this.

## 5. Back to the owner

One line now (this word recorded, the route re-dated, the answer to 4.3); one line at each of: candidate made, package
test started, package test ended (with the result), release made (what was pushed and where), demo rebuilt (checks
passed, and what waits for the owner). If the run stops: the step, the reason and what is needed, at the top of
`MORNING.md`.
