# Platform · P7 handoff (10 November 2026, ~18:25 GMT; moved to a session on the test server)

> **Superseded** (11 November 2026). Its items 1 and 6 were done on the server (SERVER_LOG.md, 11 November);
> items 2–5 are **P7a**'s under ADR-142 Amendment 8, listed in ADR-148 Amendment 1's "Left". The kind cluster it
> describes is down. Read REPORT.md and SERVER_LOG.md for P7's state, not this.

**Step:** P7, the `cloud-platform` profile (BRIEF.md). Branch rebased onto main 382268e; the last real commit is 07cd97f.
**Must do first:** move the schemas commit (`feat(schemas): profile cloud-platform…`) back to the branch's head (it sits below the 6 newest).

**Done, each proven:** every item in REPORT.md's table except the acceptance run. Since that report:
- reviewer points 2, 4–9, 11, 12 (see P7_RED_RECORD.md);
- 14: spec/05 has a profile row and §3c;
- 16, red first: bucket names carry a random suffix; an untagged undigested image is refused, and so are two sources for one copy;
- found on kind, red first: the lock names only the images a pod runs (LiteLLM with no engine); no `map:` is refused; `GRANT <owner> TO CURRENT_USER` before `CREATE DATABASE … OWNER` (PG16 on an RDS-like login).
165 P7 tests were green on the server at the rebase; later ones were run locally only (67 green).

**Not done:**
1. The cp-policy-check `other-uid` rule (commit before 07cd97f) still needs its red on the server: run `test_a_user_other_than_10001_is_refused` with the branch off, then on. Add it to P7_RED_RECORD.md, along with the four new render tests.
2. The acceptance run. On the server, from `~/osprey-runs/platform/OspreyFlow_Core`: `bash ../OspreyFlow_Build/process/lanes/platform/gates/p7_kind.sh accept`. Last attempt: seed_hmp_fixture got an ArcadeDB ReadTimeout because the worker node was at 3.9/4 GB. ner and Keycloak have since been moved to the control-plane node, and the worker now sits at 3.6 GB. Each accept run makes a new case; the seeds run as unit `verify`.
3. Before rerunning: the HMP dataset row is registered to `verify` by the failed run, and that is fine. If a seed refuses "held by another unit", delete that row on the stand-in: `kubectl -n platform-managed exec postgres-0 -- psql -U osprey -d ospreyflow`.
4. Compare any failure with main: the orchestrator says main's B4 seed gives 0 nodes. Also, main's `harness.apply.create_investigation` sends no dataset (422 `dataset_refused`), and its seeds default to `unit-1`, not the verify unit. Both are main's problems; report them, don't fix them here. A latent carry: `harness/render.py`'s `_KEYCLOAK_DATABASE_SQL` lacks the GRANT for Small on RDS (PG16).
5. Point 13: Calico's CRDs are accepted by kind's real API server (evidence, not a schema check). Point 18: `tofu init` needs the network, the same as `make opentofu-check` (accepted). Point 15 is mostly left alone.
6. Then: the lane-reviewer, "built at <hash>" to the orchestrator, then make test and make -k ci at the head (on the server run them directly, no stack_lease), then REPORT.md and the friction row's new lines.

**Kind cluster: still up** (`osprey-p7`, 2 nodes at 4 GB each, the control-plane untainted, the registry at localhost:5001). Its kubeconfig and tools are under `~/osprey-runs/platform.tools/`. The secrets for the acceptance run are in `acceptance.env` there (mode 600). It must be down by 20:30 (`p7_kind.sh down`), and the orchestrator told when.
**Running:** nothing. **No lease held.**
