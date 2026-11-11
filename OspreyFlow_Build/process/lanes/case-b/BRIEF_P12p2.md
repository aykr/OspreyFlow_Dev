# Case-b · brief P12 part 2 · Laurium wired into the cloud-platform profile

Written by the orchestrator, 11 November 2026, after P12 part 1 merged (2128e5b). Binds: `process/CLAUDE.md` rules 1–15,
`process/lanes/PROMPT_L.md`, ADR-142 Amendments 6–8, ADR-135 Amendments 5, 6 and 8, ADR-148 and its Amendments 1 and 5.
A credential step: two review rounds, listed for the owner.

**What (BUILD_PLAN_PARALLEL_LANES.md, "Two tracks", P12 part 2).**
- Laurium's service in the cloud-platform profile: its own Deployment and Service (your template file), its image in
  `images push`, and its egress line (to the gateway only).
- The extraction-engine setting in *Admin › Models* (P11 part 1's area: send it as a diff to platform-b if it touches
  P11's files).
- The pack's preset, where the brief named it.

**Exit.**
- A leased live case of Laurium reading a conforming answer from the client's own engine: the gateway or Bedrock
  route that P11 part 2 renders, on kind or against a stand-in that refuses what the real one refuses. The strict
  xfail for the 0.5B conformance model stays, and part 2's case is its own.
- cp-policy-check green on all three shapes with Laurium rendered; P7b renders it once you land.
- Laurium's key scoped as in part 1, never the master key; the egress to the gateway alone, red first.
- Gates once through `stack_lease.sh offline case-b`.

**Ownership (Amendment 8 decision 3).** Your template file(s) are yours. `values.yaml`, the profile's settings model,
`render.py`'s profile entry, `harness/cloud_platform/**`, `_helpers.tpl` and `storage.yaml` are platform's: send
diffs. **The test server is quiet from 12:00 UK time on Friday 13 November** until the owner's demo is over.
