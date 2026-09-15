# Handover — MantisNexus→OspreyFlow rename, git identity, and first push

Written 15 September 2026, mid-task, in case this session drops when the project directory
itself gets renamed. If you're a new session reading this: the user's computer has this repo
at `/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/mantisnexus`
— **check whether that folder still exists under that name, or has already been renamed to
`ospreyflow`** (that rename is the last remaining step below, and may be why you're reading this
at all). Either way, `cd` into it and re-run `git status` before doing anything — don't trust
this document over the live repository state.

---

## What this task actually is

The user is renaming the whole "MantisNexus" project (product name, code identifiers, docs,
everything) to "OspreyFlow". Separately, there is an unrelated pre-existing "osprey" CLI/harness
tool already named in the docs (`osprey.yaml`, `osprey apply`, `osprey bundle`, etc., in
`docs/05_DEPLOYMENT.md` / `docs/06_DECISIONS.md`) — the user confirmed this is **not** a
collision: the CLI staying "osprey" is intentional (it's the product's own CLI, named after the
product). So the one mapping applies everywhere:

```
MantisNexus  → OspreyFlow
mantisnexus  → ospreyflow
Mantis       → Osprey
mantis       → osprey
MANTIS_...   → OSPREY_...   (env var prefixes — underscore doesn't count as a word boundary)
MantisNexus_ → OspreyFlow_  (same underscore issue, e.g. "MantisNexus_Brand_Foundations")
```

This is a **full technical rename** (the user's explicit instruction) — not just brand-facing
docs/UI copy. Docker image tags, env var defaults, DB users/names, Python package name, the
FastAPI app title, ontology schema `$id`, sessionStorage keys — all in scope.

**Important context on how this task started:** an earlier session in this same conversation
was given a garbled/hallucinated summary claiming a MantisNexus→OspreyFlow rename was already
"in flight" in the repo. That was false — nothing had been renamed yet when this task actually
began. The user then confirmed they *did* want this rename done for real, from scratch. So
disregard any earlier claim you might see about a rename being "already underway" before this
document — this document is the accurate state.

---

## What's done

**Pass 1 — key config/build files** (done, reviewed):
`services/ingest/Dockerfile`, `services/api/Dockerfile`, `.github/workflows/ci.yml`, `Makefile`,
`deploy/compose/dev.yaml`, `pyproject.toml`, `package.json`, `apps/workspace/package.json`,
`uv.lock`, `package-lock.json`, `CLAUDE.md`.

**Pass 2 — source code** (done, reviewed): `packages/`, `services/`, `apps/`, `tests/` — 14 files.
Covered: ArcadeDB database name, MinIO bucket name, `MANTIS_PRINCIPAL_ID` /`MANTIS_CLEARANCE`/
`MANTIS_ORG_UNIT` env vars → `OSPREY_...`, FastAPI app title, ontology schema `$id`/title,
`sessionStorage` keys, page `<title>`, docstrings/comments. Cleared stale `__pycache__` bytecode
(gitignored, regenerates automatically — no action needed there, just tidiness).

**Pass 3 — docs** (done, reviewed): all of `docs/` (16 files) plus `.claude/commands/phase.md`
(the live `/phase` slash command — same content also appears, correctly, in
`docs/handoff/PROMPTS.md`). Fixed the `MantisNexus_Brand_Foundations` underscore case. Fixed two
mechanical "a"→"an" grammar slips the substitution introduced (`a osprey` / `a OspreyFlow` should
read "an"). Also discovered and incidentally fixed a **pre-existing inconsistency in the docs
themselves**: some files already said `osprey.yaml`/`osprey map add` while `00_ARCHITECTURE.md`
and `README.md` said `mantis.yaml`/`mantis map add` for the *same* config file — the rename
unified all of it to `osprey.yaml`.

**Verification method used each pass:** `grep -rliP '\bmantis(nexus)?\b|MANTIS'` across the
whole repo (excluding `.venv`, `node_modules`, `.git`, caches, `graphify-out`, `.impeccable`,
`Claude outputs`) came back empty after each pass. Re-run that grep yourself before assuming
this doc is still accurate.

**Housekeeping done:**
- Removed a stale, permission-blocked `.git/index.lock` (had to call
  `device_request_delete_permission` on the repo folder first — file deletion in a connected
  folder is off by default and needs one explicit grant per session).
- Copied the user's new design-system reference file from `~/Downloads/OspreyFlow Brand
  Foundations.html` into `docs/design/OspreyFlow_Brand_Foundations.html` (matching the naming
  convention `tokens.css`'s own header comment already uses:
  "Extracted verbatim from OspreyFlow_Brand_Foundations v0.1").
- Set local git identity in this repo: `user.name = "Ayan Kar"`,
  `user.email = "ayan.kar@solirius.com"`.
- Generated an SSH keypair **inside this session's local device VM** (NOT in the repo, NOT
  synced anywhere): `~/.ssh/id_ed25519_ospreyflow` (+ `.pub`), with an `~/.ssh/config` entry
  pinning `github.com` to that identity file.
  **This key only exists in this VM's home directory. If the device VM session is torn down
  (not just this chat session — the actual local sandboxed Linux VM the `device_bash` tool
  runs in), the key is gone and must be regenerated.** The public key that needs to be on
  GitHub (Settings → SSH and GPG keys) is:
  ```
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMnhoLKL+dXNQ4ORqcBo84UABb3ezDbWRxBgABCRXJD1 ayan.kar@solirius.com
  ```
  **Ask the user whether they've already added this to GitHub** before regenerating a new one —
  if they have, and this VM is still alive, nothing needs to change.

---

## What's NOT done yet — in order

1. **Confirm the SSH key is on GitHub** (see above) and **get the repo's SSH URL** from the user
   (e.g. `git@github.com:ayankar/ospreyflow.git`). The user said the private repo already
   exists; we were waiting on this URL when this document was written.

2. **Update `.gitignore`** — add these three entries (not yet done):
   ```
   Claude outputs/
   .impeccable/
   .claude/settings.local.json
   ```
   (`.gitignore` already has some Python/Node/macOS entries plus `.graphify/`/`graphify-out/` —
   append, don't replace.)

3. **Rename the project directory itself**, `mantisnexus` → `ospreyflow`, at
   `/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/`. This was
   deliberately saved for last because renaming the folder this session is mounted into may drop
   the live `device_bash`/`device_*` connection mid-task — which is exactly the scenario this
   handover document exists for. After the rename, a session (this one if it survives, or a new
   one) needs to reconnect — the connected-folder path will have changed, so
   `get_device_info`'s `connectedFolders` needs re-checking, and the user may need to re-approve
   folder access under the new path.

4. **`git add` everything, commit once, and push.** The user's own instruction, from earlier in
   this conversation, was: commit "the Phase 3 backlog, both Phase 4 checkpoints, and this rename
   pass" as one commit. (Ignore any earlier version of this instruction that mentioned a
   *separate* CI-file rename step — that was based on the same hallucinated premise mentioned
   above and is void; the rename is now already fully done as described here, there's no separate
   CI-only step left.)
   ```
   git remote add origin <repo SSH URL>
   git add -A
   git commit -m "<something covering: Phase 3 backlog, Phase 4 checkpoints, MantisNexus→OspreyFlow rename>"
   git push -u origin master
   ```
   (Branch is `master`, not `main` — confirmed via `git branch --show-current`.)

5. **Confirm GitHub Actions actually fires** on the push, and report back:
   - Whether the perf and a11y gates (`glass-perf-a11y-keyboard` job in `.github/workflows/ci.yml`)
     pass in that environment — recalibrate the perf thresholds in
     `apps/workspace/perf/perf.spec.ts` if they don't hold there (CI runners are slower/software-
     rendered compared to local hardware; this is a known two-tier measurement approach per that
     file's own docstring, not a bug if it needs adjusting).
   - Whether CI turns up any leftover `mantis`/`mantisnexus`/`MANTIS` reference the rename
     missed. (Should be none, per the verification greps above, but CI running against the fresh
     clone is the real test — this local repo has `.venv`/`node_modules` that were excluded from
     grep and could theoretically hide something the CI environment's fresh install wouldn't.)

---

## Where things live, for a fresh session

- Repo: `/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/mantisnexus`
  (or `ospreyflow` if step 3 above has already happened — check first).
- This file, once committed, will be at the repo root: `HANDOVER_RENAME_AND_PUSH.md`. Until
  committed, it's just sitting there uncommitted — check `git status` to see if it's tracked yet.
- Build/spec docs: `docs/` (see `CLAUDE.md` at repo root for the reading map).
- The build-review handover from the *previous* work stream (Phase 3 code review process,
  standing positions, open items like "the Ingest Studio prototype has not been reviewed by an
  analyst") is a **separate, still-relevant document**: `docs/SESSION_HANDOVER.md`. Don't confuse
  the two — that one is about the build/review process, this one is about the rename + git setup.
