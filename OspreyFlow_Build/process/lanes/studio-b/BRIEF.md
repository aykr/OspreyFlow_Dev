# Studio-b lane · brief L1.7a · the dulwich swap, then the Studio's tips

Written by the orchestrator, 9 November 2026 (the owner: "studio-b on the dulwich swap"), for a **fresh studio-b
session on the default account** (`ayan`). Read `process/lanes/CARRIES.md`'s studio rows and the owner's ruling of
9 November in `process/lanes/MORNING.md` (item 89) first. Opus, medium. Size S.

**The lane.** As L1.8, plus, by agreement with studio (which is finishing L1.5 beside you), the one file
`services/api/studio_publish.py`, its tests, and `tests/test_connectors_are_carried_into_the_image.py`. The
Conduit's Dockerfile and the licence gate's AWAITING_OWNER entry are platform's: hand them back as a carry (git
leaves the image and the entry goes, after this merges). Test stacks are on the server only; Docker is off on this
Mac. Ask the orchestrator for stacks and before heavy local runs. `make test` runs on the server through
`stack_lease.sh offline studio-b -- …`. Report by message.

**Build, in this order:**
1. **The dulwich swap** (the owner's ruling, item 89): replace `_run_git`'s `git` CLI calls (init, add, commit of
   `recipes/<id>.yaml` on the recipe volume) with dulwich under its Apache-2.0 licence. The repository on disk stays
   the record (spec 09 §6) and is byte-compatible: a `git log` on it reads the same history. Add dulwich to the
   lock and licence-check it (Apache-2.0). Tests first: publish writes a commit that real git reads, red with the
   write removed; a recipe's history survives a second publish; no `git` binary is called (red with a planted
   subprocess call).
2. **Once admin's L2.7 is on main** (it applies `admin-tips.patch` and `L1.8_roles_words.patch`): land
   `L1.8_studio_tips.patch`, `L1.8_action_registry.diff` and `L1.8_every_harness.diff` (ADR-145 Amendment 7), in
   `L1.8_PATCHES.md`'s order, with keyboard and axe re-gated. The orchestrator tells you when L2.7 has merged.

**Exit.** Both parts merged, or part 1 with part 2 waiting for L2.7; `make ci` and `make test` green; a friction row.

**Then, from ADR-148 (the owner's client decision, 9 November):**
3. **L1.10, the deployment's marking ceiling** (ADR-148 decision 10), when parts 1 and 2 are done:
   `deployment.highest_marking` (defaulting to the scheme's highest); a load or an import marked above it refused
   before anything is written, in words naming the limit, never the content; System shows the ceiling. Red at each
   entry point first; nothing written on refusal (plant a row above the ceiling); a load at the ceiling passes. The
   drawn-item check is case-b's (CARRIES).
4. **L1.9, S3 and Athena connectors**, only after platform's P7 merges (it needs the profile's egress list):
   read-only; S3 (CSV and Parquet under a prefix) and Athena (a named query or a table, paged); the namespace's IAM
   role, never a stored key; the host on the egress allow list only when the source is enabled; an ADR-140
   amendment, reserved through the orchestrator when you start. Golden files on synthetic data in an S3 stand-in;
   Athena against a recorded fixture; another dataset's source refused; the byte cap; keyboard and axe.
