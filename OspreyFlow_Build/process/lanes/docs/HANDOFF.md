# docs lane · handoff at the pause (11 November 2026, the move to the sol account)

**Step:** D2c (`process/lanes/docs/BRIEF_D2c.md`), part 2, waiting for P10. Branch `lane/docs-d2c`; its last real commit
`fb6b02c` is merged on main as `bb47f77`. Nothing ran at the pause: no stack, no lease, no server run, no subagent.

**Done (on main):**
- D2d: user guide 1.46, administration guide 1.72 (merged `ad0f699`).
- D2c part 1: the administration guide 1.76 §6a, *Deploying into a namespace on a shared platform: `cloud-platform`*, with
  spec 10's mirror word for word. Its records are under `process/lanes/docs/gates/`: `d2c-p1-guide-commands.txt` (each line
  run verbatim), `d2c-p1-docs-tests.txt` and `f07e101.{ci,test}.txt`.

**Next (the orchestrator says when each lands):** P10 first. §6a gains Entra ID: the claims mapped for clearance, unit and
handling codes, its egress endpoints, no Keycloak. Then remove Keycloak's group 0, the "identity step" gap and Keycloak's
rows from §6a.1–6a.5, and strike Entra from §6a.7. Then each of P9 (backups and restore), P9b (runbooks), P11 part 2 (the
gateway by default, its own IAM role for Bedrock: MORNING 37 item 4), P12 part 2 (Laurium: its container, image and
repository, and the list of corrections to the page shared with the client), L1.9 part 2 and P8. P7b's rulings (MORNING 37
item 5: no OpenSearch on the poc shape; the ceiling defaulting to OFFICIAL-SENSITIVE) also go into §6a once P7b merges.

**How each part goes:** write from the merged code and a render of the guide's own example, not from the ADR. Run every
command as the guide prints it. Bump the version (`tools.docs_pdf` refuses a changed guide at an unchanged version). Remake
only the changed PDF, restoring the other three PDFs and their manifest entries. Send "built at <hash from git>", start
a lane-reviewer, fix both reviews, rebase, run the gates once on the server (`stack_lease.sh offline docs`), then send
ready-to-merge with hashes copied from `git rev-parse`.

**Do not redo:** D2d, D2c part 1. **Open questions:** none.

**On this Mac:** the installed `ospreyflow` does not import (`httpx`), so use the checkout's own CLI
(`PYTHONPATH=cli python -m ospreyflow.main`). `tools.cp_policy_check` needs Docker.
