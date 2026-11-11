# studio-b · server log · L1.9 part 1 (11 November 2026)

Session on the test server, `~/osprey-srv/studio-b`, branch `lane/studio-b-l19` from main at `459ae1d4`. No
orchestrator while the laptop is offline (about 07:15 to 11:00 UTC). Plan: `L1.9_PLAN.md`.

## Log

- 06:35 Read process/CLAUDE.md, PROMPT_L, ADR-148, ADR-142 Amendment 8, the build plan's row L1.9 and 09 §2.
  Plan written. `botocore==1.43.114` (the version uv.lock already holds) installed into this worktree's own
  `.venv` only.

- 06:40–07:20 Back end, test first: `s3_connector.py`, `athena_connector.py`, `connector_reads` wiring,
  `pyproject.toml` (`botocore>=1.43.114`, its mypy override). Offline: 20 S3, 24 Athena, 14 route-level access
  cases, each file red first against a stub, then six plants at the real call sites (`L1.9_RED_RECORD.md`).
  Commit `c2d4dae9`.
- 07:20 SeaweedFS stand-in `studio-b-seaweedfs` (the build's own pinned `chrislusf/seaweedfs:4.48`, port
  127.0.0.1:58333, identities from `tests/connectors/golden/seaweedfs_s3.json`). The first green was not a result:
  a missing bucket was told as "no object"; fixed, two live plants red, then 6 passed. **Container stopped, not
  removed** (`docker rm` needs a permission this session was not given; it holds only synthetic objects, which
  the test deletes in teardown). Anyone may `docker rm studio-b-seaweedfs`.

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

4. **The Athena fixture is "recorded" from AWS's documented shapes, not captured.** No AWS account is reachable
   from this build. `golden/athena/recorded.json` says so; `test_athena_connector_live.py` (skipped unless
   `OSPREY_ATHENA_LIVE` is set, on the client's platform) is what confirms the refusals. In particular whether
   Athena reports a syntax error as a FAILED execution (modelled) or an InvalidRequestException at the start
   (also handled, in words) is unconfirmed: rule 15's "where the answer is not known, that is itself the finding".
5. **A named query runs only if it is one SELECT (or WITH … SELECT)**, comments set aside, any inner `;`
   refused (even inside a quoted value: fails closed), saved in the connection's workgroup and against one of its
   databases. The alternative (trust the role to be read-only) was rejected: a read-only connector should never
   send a write. The role being read-only is part 2's IAM policy, belt and braces.
6. **Rows from several S3 objects are unioned by column name**, first-seen order (as the JSON connector does); a
   header naming a column twice is refused. No column records which object a row came from (the SQL and API
   connectors carry none either); say if provenance should name the object.

## Questions held (for the orchestrator)

1. **An ADR-140 amendment number** for L1.9 part 1 (the row names "ADR-140 amendment (to reserve)"). The text
   is drafted in `L1.9_ADR-140_amendment_draft.md`; 09 §2 carries the as-built prose meanwhile.
