# P11 part 2's red record (rule 15)

Offline on the Mac, closed ports, 11 November 2026, from `OspreyFlow_Core`.

## Before any code
`tests/harness/test_cloud_platform_gateway.py` against main 1d97ea9: 13 failed, 4 passed. The gateway was not
rendered with no engine; no pod ran as the gateway's account; no `terraform/gateway.tf` existed (so each planted-fault
case failed for having nothing to plant into). The four passing were the no-model-host and without-Bedrock cases,
already true on main, held now that the gateway runs by default.

## Carried from part 1
`test_model_engine_kinds.py` before the schema change: `reference-words-and-token`, `path-upper-hex`, `path-base32`
and the leak sweep (with `eyJhbGci` and the hex token among its fragments) red, 4 failed.

## The plants (`p11/plant.py R1-R6 W1-W8`, raw: `plants-R-W.raw.txt`)
14 of 14 red, each restored after. R1-R6 are round 2's and its review's (the path token in one case, a token among
words, a padded or encoded JWT, a JWE, ENGINES_AS on any profile, the host row by name), whose reds were prose only;
W1-W8 are part 2's (the gateway only with an engine, a model host with none, no gateway account, the trust bound to
the namespace's account, an S3 action, every region's models, a role with no Bedrock, the gateway as the namespace's
account). W3 also turns the four formerly expected failures red again: they need the identity.
