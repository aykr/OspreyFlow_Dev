# studio-b · server log · L1.9 part 1 (11 November 2026)

Session on the test server, `~/osprey-srv/studio-b`, branch `lane/studio-b-l19` from main at `459ae1d4`. No
orchestrator while the laptop is offline (about 07:15 to 11:00 UTC). Plan: `L1.9_PLAN.md`.

## Log

- 06:35 Read process/CLAUDE.md, PROMPT_L, ADR-148, ADR-142 Amendment 8, the build plan's row L1.9 and 09 §2.
  Plan written. `botocore==1.43.114` (the version uv.lock already holds) installed into this worktree's own
  `.venv` only.

## Decisions taken (the owner may overrule)

1. **No credential field on either kind.** Options: (a) none, the deployment's own cloud identity (pyarrow's
   and botocore's default chains: in part 2 the namespace's IAM role for service accounts); (b) a named
   secret like SQL's. Chose (a): ADR-148 and the row say "never a stored key". Part 1's tests give the
   stand-ins' test credentials through `Readers` (a test seam), never through settings.
2. **No endpoint field.** The host is derived from the region and bucket (`<bucket>.s3.<region>.amazonaws.com`,
   `athena.<region>.amazonaws.com`), so there is no user-given host to point inside the deployment, and the
   egress allow-list names exactly what the SDK contacts. Bucket names with a dot are refused (virtual-host
   TLS cannot verify them). The SeaweedFS stand-in is reached only through the test seam.
3. **botocore for Athena** (Apache-2.0, already in uv.lock); S3 through pyarrow's S3 filesystem (no new
   dependency). The alternative, signing SigV4 by hand over httpx, was rejected: hand-rolled request signing
   and web-identity sign-in is where part 2 would go wrong.

## Questions held (for the orchestrator)

1. **An ADR-140 amendment number** for L1.9 part 1 (the row names "ADR-140 amendment (to reserve)"). The text
   is drafted in `L1.9_ADR-140_amendment_draft.md`; 09 §2 carries the as-built prose meanwhile.
