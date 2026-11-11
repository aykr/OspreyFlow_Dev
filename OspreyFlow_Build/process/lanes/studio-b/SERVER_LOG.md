# studio-b · server log · L1.9 part 1 (11 November 2026)

Session on the test server, `~/osprey-srv/studio-b`, branch `lane/studio-b-l19` from main at `459ae1d4`. No
orchestrator while the laptop is offline (about 07:15 to 11:00 UTC). Plan: `L1.9_PLAN.md`.

## Log

- 06:35 Read process/CLAUDE.md, PROMPT_L, ADR-148, ADR-142 Amendment 8, the build plan's row L1.9 and 09 §2.
  Plan written. `botocore==1.43.114` installed into this worktree's own `.venv` only (see request 2: the lock
  does not yet carry it for the Conduit).
- 06:40–07:20 Back end, test first: `s3_connector.py`, `athena_connector.py`, `connector_reads` wiring,
  `pyproject.toml` (`botocore>=1.43.114`, its mypy override). Offline: 20 S3, 23 Athena (24 with a case added
  after), 16 route-level access cases (8 tests × 2 kinds). The two connector files red against stubs first; the
  route file's red is its plants (`L1.9_RED_RECORD.md`). Commit `c2d4dae9`.
- 07:20 SeaweedFS stand-in `studio-b-seaweedfs` (the build's own pinned `chrislusf/seaweedfs:4.48`, port
  127.0.0.1:58333, identities from `tests/connectors/golden/seaweedfs_s3.json`), started as the brief asked
  (named studio-b-*, no lease: it is no shared stack). The first green was not a result: a missing bucket was
  told as "no object"; fixed, two live plants red, then 6 passed. **Stopped, not removed** (`docker rm` and
  `docker start` need a permission this session was not given). Anyone may remove it.
- 07:30–07:55 Glass: the wizard's S3 folder and format and Athena's table or named query (Studio's, committed);
  Admin › Connections' two kinds (no key field; the cloud role's words read with Region). Vitest, tsc, ESLint
  clean; keyboard (slot 11) 58/58 in `admin.spec.ts` and `sources-connectors.spec.ts`: four new tests proving
  five registry ids, one plant red; axe on the four new states in dark, light and GOV.UK, 20/20.
- 08:05 Own lane-reviewer on the branch: 18 findings, "merge: no". Fixed in this round:
  1. **uv.lock** does not carry botocore for the Conduit (only through the `extraction` extra), so the image's
     `uv sync --frozen` would lack it and the Conduit would not start. The brief says the lock is re-made at
     merge; the records that said "already in uv.lock" are corrected, and it is request 2 below. **Blocking
     until the lock is re-made.**
  2. A named query could read other databases or catalogs through its text: now every table after FROM/JOIN
     and in a FROM's comma list is checked against the connection's databases and catalog, a table function or
     anything not understood refused, before sending (15 cases, all red under the plant).
  3. Test connection said a missing bucket was fine: now the read's own listing helper.
  4. **Admin › Connections is the admin lane's** (`apps/workspace/src/admin/**`): my commits to it are reverted
     to main's (`8c3a289f`) and sent as `L1.9_admin_connections.diff` (the form, its test, the admin keyboard
     case and the admin harness's states).
  5. The bucket was asked for (HeadBucket, needing bucket-wide `s3:ListBucket`) before every read: now only when
     the listing is empty, so a role limited to a prefix still reads. The stand-in's identities grant bucket-wide,
     so a prefix-limited role is not shown against SeaweedFS: **open for part 2's IAM policy**.
  6. Athena's own words could carry an ARN (a Lake Formation FAILED reason) into the audit: ARNs and access key
     ids are now taken out; a recorded FAILED reason naming the role proves it.
  7. Licence register: `botocore` and `jmespath` added to `00_ARCHITECTURE.md` §7.
  8. The S3 endpoint is now named (`s3.<region>.amazonaws.com`, virtual-hosted), never taken from the
     environment. Addresses are not pinned, unlike SQL and API: recorded in the code and the ADR draft, the name
     being AWS's own, made from checked parts.
  9. A cap is its own typed error, `read_over_cap` (`ReadOverCap`, for every connector's caps), with fixed words
     for an author. This changes L1.6's SQL and API caps' type too (studio-b's own code).
  10–17: counts corrected; Parquet bounded by its decoded size a row group at a time; the misleading
     `StatementType` check removed; the CI health loop now fails when SeaweedFS never answers; store errors
     judged by their AWS code only; `_`-names skipped; the named query has a golden file; the Athena client is
     built off the event loop. Not changed: finding 13 (Docker without a lease, which the brief asked for), and
     18's 300-second register (as SQL's statement bound; a background read is part of the poll floor, R17).
  Six new plants, each red (`L1.9_RED_RECORD.md`); the live suite again on `studio-b-seaweedfs-2` (port 58334),
  6/6; stopped.

## Decisions taken (the owner may overrule)

1. **No credential field on either kind.** Options: (a) none, the deployment's own cloud identity (pyarrow's
   and botocore's default chains: in part 2 the namespace's IAM role for service accounts); (b) a named
   secret like SQL's. Chose (a): ADR-148 and the row say "never a stored key". Part 1's tests give the
   stand-ins' test credentials through `Readers` (a test seam), never through settings.
2. **No endpoint field.** The host is derived from the region and bucket (`<bucket>.s3.<region>.amazonaws.com`,
   `athena.<region>.amazonaws.com`), so there is no user-given host to point inside the deployment, and the
   egress allow-list names exactly what the SDK contacts. Bucket names with a dot are refused (virtual-host
   TLS cannot verify them). The SeaweedFS stand-in is reached only through the test seam.
3. **botocore for Athena** (Apache-2.0; needs the lock re-made, request 2); S3 through pyarrow's S3 filesystem
   (no new dependency). The alternative, signing SigV4 by hand over httpx, was rejected: hand-rolled request
   signing and web-identity sign-in is where part 2 would go wrong.
4. **The Athena fixture is "recorded" from AWS's documented shapes, not captured.** No AWS account is reachable
   from this build. `golden/athena/recorded.json` says so; `test_athena_connector_live.py` (skipped unless
   `OSPREY_ATHENA_LIVE` is set, on the client's platform) is what confirms the refusals. In particular whether
   Athena reports a syntax error as a FAILED execution (modelled) or an InvalidRequestException at the start
   (also handled, in words) is unconfirmed: rule 15's "where the answer is not known, that is itself the finding".
5. **A named query runs only if it is one SELECT (or WITH … SELECT) reading only the connection's databases**,
   comments set aside, any inner `;` refused (even inside a quoted value: fails closed), saved in the
   connection's workgroup and against one of its databases. The strict option for access (Prompt L): the
   alternative, leaving the limit to the role's IAM policy, would loosen access control, so it is not taken.
   The checker fails closed: a query it does not understand is refused, which may refuse a legitimate one.
6. **Rows from several S3 objects are unioned by column name**, first-seen order (as the JSON connector does); a
   header naming a column twice is refused. No column records which object a row came from (the SQL and API
   connectors carry none either); say if provenance should name the object.
7. **Admin › Connections' form goes as a diff** to the admin lane (the ownership map), not committed; until it
   lands, S3 and Athena connections are named through the route alone (`POST /v1/admin/connections`).

## Questions held and requests (for the orchestrator)

1. **An ADR-140 amendment number** for L1.9 part 1 (the row names "ADR-140 amendment (to reserve)"). The text
   is drafted in `L1.9_ADR-140_amendment_draft.md`; 09 §2 carries the as-built prose meanwhile.
2. **Re-make `uv.lock` at merge** (`uv lock`) so `ospreyflow` depends on botocore directly; without it the
   Conduit's image lacks botocore and the Conduit fails to start. A shared commit, not this lane's.
3. **Apply at merge:** `L1.9_admin_connections.diff` (admin lane's files; with the ADMIN ids of
   `L1.9_action_registry.diff`), `L1.9_action_registry.diff`, `L1.9_every_harness.diff`, `L1.9_ci.diff`.
4. Anyone may `docker rm studio-b-seaweedfs studio-b-seaweedfs-2` (both stopped, synthetic objects only).
