# Demo lane · brief rebuild · osprey-small rebuilt from main for the owner's demo (Part 1 only)

Written by the orchestrator, 12 November 2026, at the owner's request, for a **fresh demo session on `sol`**. This
lane exists for one job: Part 1 of the owner's rebuild prompt
(`Claude outputs/ospreyflow_demo_sites_2026-11-12/5_PROMPT_ORCHESTRATOR.md`, as amended below). Read that prompt
and this brief first; **where they differ, this brief wins**. Opus, medium.

**You are allowed to touch osprey-small, for this rebuild only.** That deployment is the owner's demo for Friday
13 November. Nothing else in this repository is yours: you write no code, change no file under `OspreyFlow_Core/`
or `OspreyFlow_Build/` except `process/lanes/demo/`, and merge nothing. You report to the orchestrator **by
message** at each stage and wait for its word where this brief says so.

## Where things are (checked by the orchestrator today)

- The server: `ssh -o BatchMode=yes ospreyflow-test` (as root). osprey-small's code is `/opt/ospreyflow`
  (owned by user `osprey`), its deployment folder `/opt/ospreyflow/deploy/generated/small`, its answers file
  `/opt/ospreyflow/install.yaml`, its compose project `osprey-small`, address `https://ospreyflow-poc.test`.
- The CLI on the server: `cd /opt/ospreyflow && PYTHONPATH=cli:.:packages .venv/bin/python -m ospreyflow.main <verb>`
  (plain `ospreyflow` is not on the path).
- Done already (Part 1.1): a backup, `/srv/ospreyflow/backups/small/20261112T160910Z-small-unknown`, verified
  by the restore's dry run (nothing restored). The v0.5.0 code is kept at `/opt/ospreyflow-v0.5.0` for a
  fall-back. Your log folder on the server: `/root/rebuild-2026-11-12/` (keep numbering from `3-`).
- Volumes: `osprey-small_ollama-models` (11 GB) and `osprey-small_whisper-models` are **kept** (the owner's
  word). Every other `osprey-small_*` volume is emptied, so the stores start fresh.
- **Small's install never makes demo accounts** (`_install_on_server`). The product's way is
  `ospreyflow repair-sign-in` (without `--no-demo-accounts`) **after** the install, which registers the four
  demo accounts and writes their sign-in details into `deploy/generated/small/deployment.env`. It must run
  **before** the demo packs, so each pack's seed can make `osprey-demo-analyst` an Editor of its case.
- The answers file takes `models.local_only` but **not** `sendable_handling_codes`. Set
  `sendable_handling_codes: [P]` in `/opt/ospreyflow/osprey.yaml` after the install, then **one**
  `ospreyflow apply` (the owner's word).
- `osprey-demo-admin` (Administrator, Analyst, Data Engineer) can **deploy** rules but not **write** them: writing
  needs the Rule author role (`author_rules`). Report it; **do not add the role** (the owner's word).
- The starter `govuk-crime` brings `prison-intelligence` and `hmp`; add `operation-ledger`, `fixture-corp` and
  `cyber-intrusion` with `ospreyflow demo add`. **Never** Enron, PaySim or any real dataset; not the PID scale
  cohort either.

## The steps (stop and message the orchestrator after each **bold** one)

1. **Wait for the orchestrator's "go", with the commit of main to install.** (Studio's step is merging first.)
2. Copy main's `OspreyFlow_Core` at that commit to `/opt/ospreyflow` on the server (rsync from your worktree at
   that commit, as user `osprey`; keep `.venv` and re-sync it with `uv sync --frozen --extra extraction`;
   keep `install.yaml`; never copy a local `osprey.yaml` or `deploy/generated/` over the server's).
   Record main's commit in `3-code.txt`.
3. `ospreyflow uninstall --keep-data --yes`, then remove every `osprey-small_*` volume **except**
   `ollama-models` and `whisper-models`. Record the volumes before and after.
4. Edit `install.yaml` (keep a copy as `install.yaml.before-rebuild`): `components: {dashboards: true}`,
   `models: {local_only: false}`, `demo_packs: []`, starter `govuk-crime`, the same `server:` and
   `appearance:`. Then `ospreyflow install --mode small --answers install.yaml --force
   --first-admin-code-file /root/rebuild-2026-11-12/first-admin-code` (mode 600). **Never print or copy
   the code**; the owner reads it from that path. **Install done: message.**
5. `ospreyflow repair-sign-in` (with demo accounts). Then `sendable_handling_codes: [P]` in osprey.yaml, then one
   `ospreyflow apply`.
6. `ospreyflow demo add` for `prison-intelligence`, `hmp`, `operation-ledger`, `fixture-corp`,
   `cyber-intrusion`, each into its own case. **Packs loaded: message.**
7. The owner's checks, each result listed (pass, or fail with its evidence):
   - every service healthy (`ospreyflow status`, `docker ps`);
   - sign-in works for each of the four demo accounts. Use the Keycloak sign-in form as the Glass does, scripted
     on the server, reading the passwords from deployment.env without printing them;
   - each demo pack is loaded: per case, its counts of entities, links, events and documents against what the
     pack should give (the pack's own expected counts or its seed's);
   - `osprey-demo-analyst` can open every demo case and is an Editor of each;
   - the prison intelligence case has its documents, and the local model answers a question asked in Questions
     as `osprey-demo-analyst` (say the model and the time taken);
   - the Operation Ledger case has its screening lists and its alerts in the queue;
   - the dashboards open inside a case for `osprey-demo-report-viewer`;
   - `osprey-demo-admin`'s rule rights, as above.
   **Checks done: message, with the list.**
8. Then **change nothing**: the owner walks the demo script tonight. Freeze it. Nothing of yours runs on the server
   from 12:00 UK on Friday 13 November.

## If anything fails

Message the orchestrator **at once**, with the step, the evidence and your recommendation: a fix tonight, or the
fall-back (a reinstall at v0.5.0 from `/opt/ospreyflow-v0.5.0`, about 1½ h). Do not start either without the
orchestrator's word. The owner wants the result **by 20:00 UK** tonight.

## Never

- No password, one-time code, key or access code in any message, file you commit, or log you print. Give paths
  only: the admin code is at `/root/rebuild-2026-11-12/first-admin-code`, and the demo accounts' details are in
  `deploy/generated/small/deployment.env`.
- No lane stack, no `stack_lease.sh` run, nothing on any other deployment or container (`osprey-test-*` are the
  lanes'). No push. No real data.
- Nothing reachable from the internet: the server stays as it is (443 for osprey-small; the rest is Part 2's).
