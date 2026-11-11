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
- **The plants:** `plants-R-W.raw.txt`, `p11/plant.py R1-R6 W1-W12` with both diffs applied: 18 of 18 red. R6 and W7
  were first `NOT RED` because their planted lines had moved with round 1's refactor (`engine_host`,
  `bedrock_enabled`) and so planted nothing; re-aimed at the lines as they stand, both red for their stated reason.
- **The policy check:** eighteen planted shapes in `test_the_policy_check_flags_each_fault_planted`, each caught,
  the real file faultless (an S3 action, `*`, `bedrock:*`, a hyphenated or capitalised service, a `*` resource,
  another region, any resource, `not_actions`, `not_resources`, a Deny, a whole `*`/`*` statement, `StringLike`,
  `StringNotEquals`, a `*` principal, no OIDC, the namespace's account, a second trust statement).
- **The ruling's refusal:** nine cases red with `_made_by_the_render` planted out (W9).
- **Item 7's words:** the Glass test's matcher red on the old words (`namespace's IAM role in London`) until changed.
- **Item 8:** the long reference refused on Lite before the scope change, then loaded (W12 plants it back).
