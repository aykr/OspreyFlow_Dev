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

## Built

**P11 part 1 built at e28c561** (code), after my own lane-reviewer's round, all its findings fixed but the
orchestrator's two (Q2 number, Q4 ownership). Reviews: the orchestrator's independent review is owed, and
this is a credential step, so two rounds. Then rebase, then the gates once at that head. `make test` here
ran on an earlier head as an interim check only (`p11/make-test-py.txt`), not the gate. Nothing running.
