# Platform-b · server log, 11 November 2026

The owner's laptop is offline (about 07:15 to 11:00 UTC). No orchestrator to message; decisions are taken
here with the recommended option and logged for the orchestrator to overrule.

## About 06:35 UTC · start (times below are the commits' own, `git log --date`)

- No other agent in `~/osprey-srv/platform-b` (`ListAgents`, `pgrep`): the five peers are in their own trees.
- `lane/platform-b-carries` was clean at cf92e93: **every carry was already built** on the Mac (the handoff:
  chart quoting 682d25f/fc16bb0, `write_private` 5fb3b31, staged refresh 1ed8b27, the lockout's words
  b0bb8cb, lint e4b24b0). What is left there is step-end work only (spec amendment numbers, REPORT, review).
- `git switch` is refused by this session's permissions; `git checkout lane/platform-b-p11` worked.
  `lane/platform-b-p11` = main 459ae1d.

## P11 part 1 · plan (from ADR-135 Amendment 4, BRIEF_P11.md, ADR-135 Amendments 2 and 3)

**An engine's kind and how it signs in**, on `ModelProviderConfig` (`packages/schemas/deployment.py`):
- `kind`: `provider` (as today: LiteLLM's provider by name), `gateway` (the client's own OpenAI-compatible AI
  gateway: `api_base` required, LiteLLM's `openai/` route), `bedrock` (Amazon Bedrock, LiteLLM's `bedrock/`
  route, no `api_base`).
- `auth`: `key` (as today; for `gateway` the key is the gateway's token, the same write-only path) or
  `iam_role` (the namespace's IAM role: **no key stored anywhere**).
- `region`: Bedrock's only, and only `eu-west-2` (London), the default for Bedrock.
- Refused in words: Bedrock with `key` (ADR-135 Am 4 (b): by IAM role, no stored key), any region but London,
  a region on a non-Bedrock kind, a `gateway` without an address, `iam_role` on a `provider`.

**The gateway entry** (`GatewayAdmin.add_entry`): `model_name` unchanged (`<engine>/<model>`); the route's
`model` from the kind; a key engine names its credential; **an IAM-role engine names none**, and Bedrock's
entry carries `aws_region_name: eu-west-2` only (the gateway's pod identity signs).

**Models' service** (`services/api/model_admin.py`): an IAM-role engine's key state is `iam_role` (a new
`KeyState`); it is offered to analysts with no key; `PUT …/key` refused (409) in words, stored nowhere;
changing how an engine signs in, its kind or region removes its key as an address change does; the
connection test runs for it, with role words where it is refused.

**The stand-in** (`adapters/model_litellm/stand_in.py`, rule 15): a client gateway at an address (refuses no
token, a wrong token echoing a fragment, a model it does not offer) and Bedrock behind the gateway pod's
identity (refuses no identity, a role not allowed, another region, a model not offered, throttling), each
refusal shown by `test_stand_in_gateway.py` before anything is trusted against it.

**Tests first, each red**: the schema's refusals; the stand-in's refusals; P1's access test and planted-key
test on both kinds; no key stored for an IAM-role engine (gateway rows, models file, credential table);
P2's limits on both kinds; the UI (*Models*' kind and sign-in choice, no key field for an IAM-role engine),
keyboard (rule 13) and axe in three themes.

## Progress

- 06:45 c622caa: the stand-in's client gateway and Bedrock, each refusal shown first; the connection check
  reads Bedrock's refusals (2 red at the real classifier before).
- 06:53 49caf7c: the schema, the Models service, the CLI's key move, routing, and the `osprey.yaml` path
  (render, install, install page); 23 red before, 8 faults planted at their call sites (`p11/RED_RECORD.md`).
- 07:02 9c34f86, 0bc9432: *Models*' form (kind, the gateway's sign-in, no key controls for an IAM-role
  engine), vitest 3 red then green; keyboard 2 new cases (13/13 green, red with the key button planted back);
  axe on two new states in dark, light and GOV.UK; the generated types. (First written "36/36 axe": it was
  27 axe scans and 9 label checks over the 9 *Models* states; corrected on the reviewer's count.)
- 07:02 a799f34: E501 on my lines. ruff check and mypy clean on the branch's Python diff; tsc and eslint clean.
- 07:03 to 07:10: my own lane-reviewer on 2ea4e79 (read-only). **It would not let it merge**: 2 blocking,
  8 must-fix, 7 minor. Blocking: (1) a key held under an IAM-role engine's name stopped being blanked in
  other services, since the "keyed" list I narrowed was also the blanking list (on a cluster the Secret
  keeps it for good, so api and every worker could read an old token); (2) an engine named `bedrock` of kind
  `provider` validated and reached Bedrock by a stored key in no fixed region. Must-fix: a declared IAM-role
  engine never got gateway entries (no key to move); a kind change on edit carried one processor's DPA mark
  to another; the gateway by the IAM role offered to analysts though it cannot be reached; the CLI hid
  IAM-role engines and still read a key for them; the stand-in lacked STS's and the inference profile's
  refusals and still said "every behaviour measured"; the schema commit not at the head; files outside the
  map (my decision 5); rule 11, friction and report owed.
- 07:10 to 07:45, 5773a0b then the split: every finding fixed but the ownership ruling and the number (the
  orchestrator's), each with a new test red first and the fix planted back out (plants A to L,
  `p11/RED_RECORD.md`); the minor ones too (remove-key refused, honest `move` words, a refused reconcile
  recorded as no key, the install page tested, type-ahead in the keyboard case, the unused words dropped).
  708 tests across the model, harness and CLI suites green; vitest 9/9; keyboard 13/13; axe 27 + 9 green;
  ruff, tsc, eslint clean; mypy clean on my lines (its five CLI errors are at lines this branch never
  touched). Then **the branch re-cut into six commits with the schema change at the head** (e28c561), the
  tree identical (the old history in `p11/pre-split-history.txt`; its head kept as the local branch
  `p11-pre-split-0383b63`).

## Decisions taken (the recommended option each time; the orchestrator may overrule)

1. **Kind and sign-in as two fields** (`kind`, `auth`) plus Bedrock's `region`, rather than new provider
   names: a client gateway needs a name of the client's choosing and LiteLLM's `openai/` route; `auth` is
   separate because Amendment 4 (a) allows either a token or the role for the same kind.
2. **The client's gateway by token reuses the key path whole** (write-only, one credential, address change
   removes it): a token is a key to the gateway, and a second secret path would be a second thing to review.
3. **A sign-in or region change removes the key**, extending the owner's address ruling, and **the kind is
   fixed once added** (after the review: another kind is another processor, which the DPA mark does not
   cover). Strict options.
4. **A key line for an IAM-role engine is skipped and named** by `move_keys` (as a removed engine's is) rather
   than refused, which would fail every `apply`; the Models route itself refuses it (409).
5. **The `osprey.yaml` path carries the kind** (render → Conduit, install, install page): without it a
   declared Bedrock engine came back as a keyed provider and stopped the install for want of a key. Small
   one-line changes in `harness/{render,apply,install_page}.py` and `model_routing.py`, beyond Admin › Models
   itself; named here for the ownership ruling.
6. **Fixtures recorded, not measured** (rule 15): no client gateway or AWS account is reachable from here.
   Each refusal is modelled from documented answers and shown first; part 2 measures Bedrock for real.
7. **Gates' locale:** the existing keyboard case "the usage's period … days" types `02112026` and fails on
   this server's US date order (a pre-existing environmental fault, not this change); run with
   `LANG=en_GB.UTF-8` it passes, 13/13.
8. **The gateway by the IAM role is refused for now** (after the review, the strict option): offered, it
   would be a default analysts could pick that fails every call. *Models* says "a token for now".
9. **The branch re-cut with `git reset --soft main`** (no interactive rebase here) to put the schema commit
   at the head, as PROMPT_L asks; nothing pushed, so no one's history moved.

## Questions held for the orchestrator

- **Q1 (for the owner, through the orchestrator): the client's gateway by the namespace's IAM role.** LiteLLM's
  OpenAI route sends nothing without a key, so this sign-in is **refused for now** (decision 8). How the
  client's gateway takes the identity (SigV4, or the pod's web-identity token as a bearer) is the client's
  to say. Recommended: ask the client; the schema keeps `auth` so it can be admitted by one refusal's
  removal once that is known and measured.
- **Q2: an amendment number** for the as-built record (`p11/ADR-135-AS-BUILT-DRAFT.md`); ADR-135 Am 6 is
  case-b's. Rule 11 is met only once it is in `spec/06_DECISIONS.md`.
- **Q3: shared files as a diff** (`p11/shared-files-P11.diff`): `actionRegistry.ts` (two MODELS_ACTIONS ids)
  and `a11y/every-harness.spec.ts` (two *Models* states), to apply at merge.
- **Q4: ownership ruling** for `harness/{apply,cluster,install_page,render}.py`, `services/api/model_routing.py`
  and `cli/ospreyflow/{main,models,doctor}.py` (eb0ea959, d1770ed9): beyond Admin › Models, needed so a
  declared IAM-role engine neither stops the install nor leaves a held key readable.
- **Q5: Bedrock measured for real** in part 2: every Bedrock refusal and the classifier's words are recorded
  from documentation, not measured (the draft says so).
- (Resolved: the schema commit is at the head, e28c561.)

## The orchestrator's review, round 1 of 2 (cec7a5e6, "not mergeable"): one pass, the code committed at 09:44 (`git log --date`)

- **Start.** No other agent in this worktree (`ListAgents`: the admin lane alone, in `~/osprey-srv/admin`;
  `pgrep`: its session and this one). `lane/platform-b-p11` at cec7a5e6 by `git checkout` (`git switch` refused
  by this session's permissions, as before). `lanes_heartbeat.sh` is refused by them too: **no heartbeat sent this
  round**. `lane/platform-b-carries` not touched.
- **The profile is not on this branch.** ADR-148's `cloud-platform` is P7's (`lane/platform`, 31 commits not on
  main); the owner's main 354bbec is not on this server either. So the rules are held to the profile **by its
  value** (`MODEL_ROUTE_PROFILE = "cloud-platform"`), which P7's `Profile.CLOUD_PLATFORM` (a `StrEnum`) equals at
  merge; `osprey.yaml` at that profile cannot be validated here, and the harness's cases for the two kinds widen
  the profile set for the test alone (decision 10). The build plan has P11 after P7 merges; the orchestrator
  reviewed and ruled on it as it stands, so I built on.
- **Item 1, the blocker:** shown red at cec7a5e6 for its stated reason (`p11/red-2-round-1-at-cec7a5e6.txt`).
  Fixed by one profile-scoped function, `engine_refusal(engine, profile)`, called by every reader of an engine
  with the deployment's profile (`osprey.yaml`, `Installed.from_env`, `ModelSettingsFile.load`,
  `ModelAdmin._validated`); the Conduit's profile is `OSPREY_PROFILE` from `deployment.env`. Every other profile
  as on main: main's own render test restored unchanged and green; `bedrock` back in *Models*' provider list.
- **Item 2:** any id with a part before the provider's, and any ARN, refused on `cloud-platform` (not only known
  prefixes: AWS's own guide warns the prefix alone does not say where a call goes). The classifier's docstring no
  longer points at inference profiles; Bedrock's "on-demand throughput isn't supported" is said as the model not
  offered on demand in London.
- **Item 3:** AWS's documentation checked for each Bedrock string (a web-fetch agent, 11 November): only the
  expired-token wording is documented, as "has expired"; "You don't have access to the model…", "The provided
  model identifier is invalid" and "on-demand throughput isn't supported" are not. The draft says so, per string,
  with the pages. The region case and the stand-in's region branch are removed (unreachable).
- **Item 7:** the two guide files restored to main by name (39f32b0b); their appendix change is
  `p11/docs-admin-guide-P11.diff`. No `make` target regenerates it (`python -m tools.admin_guide_options
  --write`, by hand), so it is not kept: `test_admin_guide.py`'s two appendix cases fail here until docs applies it.
- **Plants:** `p11/plant.py`, committed. The first run (uncommitted tree) was 46 of 47 red: **N23 was not red**,
  planted in a `render_cluster` branch that never ran (the cluster's gateway has no `envFrom`), which was this
  lane's own dead code from round one: removed, the test widened to every env shape, N23 planted again where a
  key really arrives, N25 added. A same-length plant also left stale bytecode behind (N21): the script now writes
  none. Every plant re-run at the code head: `p11/plants-bcc51186.txt`.
- **Glass:** vitest 11/11; keyboard 13/13 (slot 7, `LANG=en_GB.UTF-8`, the shared diff applied); axe 36/36 on
  the nine *Models* states in three themes, the two new ones at `cloud=1`. tsc and eslint clean; Prettier not
  run as a gate (main's own `Models.tsx` does not pass it). ruff and mypy clean on the branch's Python diff.
- **Left listening, not mine:** vite on 5893 and 5894 (slot 7's harness axe ports) from the gate runner's copy
  `/root/osprey-runs/platform-b`, started by an earlier run and not by this session: not stopped (never kill a
  process you did not start). The harness's axe target in `make -k ci` may fail on them; said with the gates.
- **Not run this round:** my own lane-reviewer (the brief here is the orchestrator's review; round 2 follows).

### Decisions taken this round (the recommended option; the orchestrator or the owner may overrule)
10. **The profile by value, the harness by a widened set.** Options: add `Profile.CLOUD_PLATFORM` here (P7's
    file and render, half-built here); wait for P7; or compare by value and widen the set in tests. Chose the
    last: nothing of P7's is copied, and P7's member equals the string at merge.
11. **Item 4's address and label refusals on `cloud-platform` only**, by item 1's ruling (every other profile
    as on main); recommended to the owner for every profile, as its own decision.
12. **Off-profile fields not written.** A plain provider's models file, `OSPREY_MODEL_ENGINES` line, request
    body and audit leave out `kind`, `auth` and `region`, so another profile's state is byte-for-byte main's.
13. **The CLI with the Conduit silent:** refuses `key`/`remove-key` before reading a key where the engine may
    keep none (declared so, or any engine on `cloud-platform`); every other profile reads the key as before.
14. **A 4xx the classifier does not know, from the client's gateway, is `request_refused`**, given by *Admin ›
    Models* for that kind alone, so no other provider's answers change.

### Gates at bcc51186 (once)
`stack_lease.sh` (offline and every other verb) is refused by this session's permissions, so the two gates ran
with `make` here, on the offline lease's closed ports and slot 7, `shared-files-P11.diff` applied uncommitted:
- `make test`: 4 failed, 10934 passed, 13 skipped. The failures are `test_gpu_is_skipped…` (this server has a
  GPU), `test_valkey_config` (pinned 59993) and `test_admin_guide` ×2 (item 7: the appendix is docs' diff). Live
  files all collect. JS: the workspace had 2 failed, 3057 passed; the Matrix 50,000-node budget and the checks
  screen's refusal words both pass run alone, so it was load. Harness 51/51. `p11/bcc51186.test.txt`,
  `.test-js.txt`.
- `make -k ci`: every target passed except `harness-a11y`: "http://localhost:5893 is already used", the vite left
  by `/root/osprey-runs/platform-b` (above), not stopped. `p11/bcc51186.ci.txt`.
- Restored by name afterwards: `actionRegistry.ts`, `every-harness.spec.ts`, and the three
  `.terraform.lock.hcl` files `tofu init` rewrote. Docker images built as `ospreyflow/*:ci`; nothing pruned;
  `osprey-small` untouched.

## Built

**P11 part 1, the orchestrator's review round 1 fixed: built at bcc51186.** Round 2 follows.

**(Earlier.) P11 part 1 built at e28c561** (code), after my own lane-reviewer's round, all its findings fixed but the
orchestrator's two (Q2 number, Q4 ownership). Reviews: the orchestrator's independent review is owed, and
this is a credential step, so two rounds. **Addendum:** the interim `make test` found the settings appendix
generated from the schema out of date (`test_admin_guide.py`); regenerated in 8d2f18b, which is now the
code head to review. Interim result and its five failures explained in `p11/REPORT.md` item 7. Then rebase, then the gates once at that head. `make test` here
ran on an earlier head as an interim check only (`p11/make-test-py.txt`), not the gate. Nothing running.
