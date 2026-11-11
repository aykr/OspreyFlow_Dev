# Studio-b · brief L1.9 part 2 · S3 and Athena on the cloud-platform profile

Written by the orchestrator, 11 November 2026, 22:10 UTC, when P7b merged (3673660). Binds:
- `process/CLAUDE.md` rules 1–15 and `process/lanes/PROMPT_L.md`;
- ADR-148 decision 7 and Amendment 5 as merged (each workload's own egress rows, single ports, accounts by need,
  cp-policy-check);
- ADR-140 Amendment 20 (part 1 as built).

Reserved for you: **ADR-140 Amendment 21**. Size M. Account sol.

**What.** Part 1 built the readers, with no profile, IAM or egress wiring. Part 2 makes them work on the cloud-platform
profile without widening anything P7b closed.

1. **Hosts declared at install.** A cloud_platform setting declares the S3 buckets (with region and prefix) and the
   Athena workgroups (with region) a deployment may read. Choose its shape in your plan, kept beside
   `connector_hosts`.
   - The render turns each into the reading pod's own egress rows, on 443/TCP, through P7b's egress.paths. Use
     `<bucket>.s3.<region>.amazonaws.com` and `athena.<region>.amazonaws.com`, and the results location's bucket
     where one is set.
   - Find which pod runs the reads: the Conduit, the worker or both. Give the rows to that pod alone.
   - The same settings feed the Conduit's own allow-list, so the two cannot disagree on hosts.
2. **Admin refuses what was not rendered.** Enabling or testing an S3 or Athena connection whose host was not
   declared is refused in words. The words name the setting and the re-render and `helm upgrade`, as Admin ›
   Models refuses an engine the render did not make (ADR-135 Amendment 8). Red first.
3. **IAM, read-only and scoped.**
   - The Terraform the profile renders gains the read statements the readers need:
     - s3 ListBucket on the declared bucket, conditioned on the prefix;
     - GetObject under the prefix;
     - athena Start/Get/StopQueryExecution, GetQueryResults and GetNamedQuery on the declared workgroups;
     - glue Get on the declared databases;
     - Put on the results location only.
   - They are rendered only when a source is declared. No `*` resource and no write outside the results location.
   - Attach them to the account the reading pod already has (P7b: IRSA belongs to api, worker and report-sync
     alone); give no other pod a new account.
   - Add a test that refuses a wildcard resource, and a plant.
4. **Region refusals (CARRIES row 150).**
   - Real S3 answers a wrong region with PermanentRedirect or AuthorizationHeaderMalformed; SeaweedFS ignores regions.
   - Model those refusals in the fakes from AWS's documented responses, and record that they are modelled, not
     measured (rule 15).
   - The reader turns each into typed words, never a retry loop or an empty read.
   - Do the same for Athena's FAILED against InvalidRequestException on an unparseable query.
5. **cp-policy-check stays at 0 violation(s)** on all four fixtures. Give a fixture with a declared S3 and Athena
   source its own clean render.

**Not in scope.** No other profile changes (local-lite, small and cluster renders byte for byte). No stored key, ever
(part 1's rule). No Glass change beyond the refusal words, which are a glass diff if they touch `apps/workspace`.

**Ownership.**
- Yours: the connectors (`services/ingest/connectors/`, `connector_reads.py`).
- Shared, so send diffs: `values.yaml`, the settings model, `render.py`'s profile entry and `harness/cloud_platform/**`
  (platform's, now free); the Glass (glass's).
- The schemas commit goes at the head.

**Exit.**
- Each item red first.
- cp-policy-check 0 on every fixture.
- The renders of the other profiles unchanged.
- Amendment 21 written.
- Gates once through `stack_lease.sh offline studio-b`.
- A docs line for D2c's queue, sent to the orchestrator.
- Send "built at <hash>" by message.

**The server is quiet from 12:00 UK on Friday 13 November** until the owner's demo is over: no runs then.
