# P11 part 2's red record (rule 15)

Offline on the Mac, closed ports, 11 November 2026, from `OspreyFlow_Core`.

## Built (ee6e524)
`tests/harness/test_cloud_platform_gateway.py` against main 1d97ea9's `harness/cloud_platform`: red for the gateway
not rendered with no engine, no pod as the gateway's account, and no `gateway.tf`. The figure first written here
("13 failed, 4 passed") was not from a kept output and is withdrawn: the orchestrator's and my reviewer's reading
gives 11 failed and 6 passed (the keyed and client-gateway account cases already true on main). The raw count that
stands is the one below.

## After round 1 (rebased onto main ff0e07d, at bf6e796)
- **Which cases need `cloud-platform-P11p2.diff`:** `without-the-diff-bf6e796.raw.txt`, the three test files run
  on the branch alone: 64 failed, 175 passed. Many more than part 1's eight, because the test world is now built from
  the real render of what `osprey.yaml` declared (the blocker's fix), which needs the diff to render Bedrock at all.
- **The plants:** `p11/plant.py R1-R6 W1-W12` with both diffs applied: 18 of 18 red (superseded by `plants-all.raw.txt`, below). R6 and W7
  were first `NOT RED` because their planted lines had moved with round 1's refactor (`engine_host`,
  `bedrock_enabled`) and so planted nothing; re-aimed at the lines as they stand, both red for their stated reason.
- **The policy check:** eighteen planted shapes in `test_the_policy_check_flags_each_fault_planted`, each caught,
  the real file faultless (an S3 action, `*`, `bedrock:*`, a hyphenated or capitalised service, a `*` resource,
  another region, any resource, `not_actions`, `not_resources`, a Deny, a whole `*`/`*` statement, `StringLike`,
  `StringNotEquals`, a `*` principal, no OIDC, the namespace's account, a second trust statement).
- **The ruling's refusal:** eight cases red with `_made_by_the_render` planted out (W9; nine selected, one the gateway's no-role case, which W3 holds).
- **Item 7's words:** the Glass test's matcher red on the old words (`namespace's IAM role in London`) until changed.
- **Item 8:** the long reference refused on Lite before the scope change, then loaded (W12 plants it back).

## Round 2 (the orchestrator's, on 223e8c5)
- **An engine from the models file the render did not make** (a restore): `test_a_restored_engine_the_render_did_not_
  make_is_never_written_or_offered` red first (Bedrock's entry written into the gateway at start), and
  `test_on_cloud_platform_with_no_word_from_the_render_every_engine_is_closed` red first (Gemini written with no
  `OSPREY_MODEL_ROUTES_MADE`). Planted back: W13 (the gateway write), W14 (the offer to analysts), W15 (`set_key`).
- **The Glass's marking:** the `role="note"` case red with its line planted out.
- **The CLI's words:** `test_models_verb_iam_role.py`'s two cases, asserting the new words, red on the old.
- **A stray reference to the gateway's role, policy or account in another Terraform file:** three planted strays
  (the gateway's policy on the bucket role, the bucket policy on the gateway's role, the gateway's account in
  another trust), each caught; none in the real files.
- **The Conduit's host placement held to the render's:** five engines, `{region}` and the default region included.
- **`p11/plant.py` runs clean:** `plants-all.raw.txt`, every plant but the keyboard pair: 69 of 69 red. Five (6, E,
  K, N6, N10) had first planted nothing, their lines reworded by round 1 (the gateway's own role, `ENGINES_AS`'s
  profile, the label's per-word check), and were re-aimed; the runner now keeps every FAILED line.
