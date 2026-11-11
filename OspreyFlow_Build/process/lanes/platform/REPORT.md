# Platform lane · P7b · report (11 November 2026, the Mac; after the orchestrator's final review and its second pass; the kind run waits for P11/P12 part 2)

**Ready to merge at `2833a66fdf0ec6f0a057c27a70d606d86d45edd1`** (tree `d934d463777f`), on main fe22804. The
`connector_hosts` schemas commit sits before the render commit that imports it, so every commit builds; the other three
schemas commits are at the head. The commit above it holds this report, the server log, the gates' outputs and the
guide's diff alone. Every run went through `stack_lease.sh offline platform` (no stack, no lease). Nothing running;
nothing pushed. Merge order (the orchestrator's): P7b first, then P9, then case's `P9_decommission.diff`, then P12 part 2
with its `laurium` row.

| Exit criterion | State | Proof |
| --- | --- | --- |
| `cp-policy-check` green | Met: development 57 manifests, poc 49, production-bedrock 64, production 64, each 0 violation(s); `make -k ci` exit 0 | `gates/2833a66f.gates.txt` (the gate's lines unfiltered) |
| …red on each planted fault | Met: 106 plants, 106 red, each in Helm's own output or at its call site | same |
| Each workload's own egress, ingress, secrets and token (Am 5 points 21-24) | Met: the evaluator applies Calico's order to Helm's output, every pod to every pod, host (on its own ports and no other), network, the internet and DNS | `test_cp_egress_order.py` |
| The final review's items, both passes | Met, each red first (Am 5 points 21-24 say each) | `test_cp_policy_check.py`, `test_cloud_platform_egress.py` |
| Decommission leaves nothing behind, red first | Check built; the backups kept by P9's diff at merge (Am 5 point 20) | `test_cp_decommission_check.py` |
| Runbooks end to end on kind; acceptance on kind | **Not yet**: after P11/P12 part 2; until then syntax, order and rights only | Am 5 "Left" |
| The other profiles' renders unchanged | Met: against fe22804 local-lite, small and cluster are byte for byte | `gates/2833a66f.renders-full.txt` |
| The cloud-platform renders' standard shape unchanged (P7b's brief) | **Superseded by the orchestrator's rulings** (Am 5 points 21-24): the two cloud-platform configurations differ by the ruled rework, every changed line recorded | `gates/2833a66f.renders-full.txt` |

**Gates at 2833a66f.**
- The cp suite, the cloud-platform harness tests, the images verb and the model-engine tests: 587 passed.
- `make -k ci`: exit 0; its cp-policy-check lines are recorded unfiltered.
- `make test`: 3 failed, 12171 passed, each known: the GPU preflight case (the server has a GPU); `test_admin_guide`'s
  appendix, which `P7b_admin_guide.diff` makes green (rebuilt against main's docs); `test_render_memory`'s OpenSearch
  case, main's own (in CARRIES).
- Corrected earlier (the final review's item 8): at a5d580a0 `make -k ci` failed two targets, `harness-a11y` and
  `cp-policy-check`, not `harness-a11y` alone.

**Decisions taken:**
- "A scratch volume for Ingest" is the Ingest root's own claim (agreed).
- The kept backups come through case's `P9_decommission.diff` at merge (agreed). `backup/platform-p7b-with-kept-hooks`
  is kept until then.
- Keycloak holds no token (agreed).
- A host's ports: 443 for the AWS services and the engine kinds' hosts, an address's own or its scheme's, `mail.port`,
  and `connector_hosts`' `host:port`, a bare host on 443 and named in words at the head of `values.yaml` (and in the poc
  shape's INSTALL.md); an IPv6 literal is refused. A host given twice with two ports is one row with both ports.

**For the lanes after this one:** P9's four pods set their own `serviceAccountName` (never the bucket role's or the
gateway's) and `automountServiceAccountToken: true`, and need no edit at `egress_policy`. P12 part 2 adds
`paths.laurium: [litellm]` and `laurium` to `paths.api` alone; Laurium holds no key of ours unless listed in
`NAMED_SECRET_ALLOWED`. A new Calico rule names its protocol and single ports and selects by workload name.

**Carried** (seven new CARRIES rows): the operator docs (D2c); Admin › Connections' port warning; IRSA's webhook and the
API token; identity by label; the renders comparison as a lane script; the ingest ceiling's unset reading; which pods
read the platform's own Terraform-made Secrets (a question for the platform team). Also still: the standard shape's
OpenSearch domain; the seeds' ceiling (studio-b); the identity step against a real Keycloak; the kind rehearsal's
stand-ins for the platform's blocks.

**Requests:** apply `P7b_admin_guide.diff` at merge (admin guide 1.82 redone); mark Am 5 written (points 1-24); ratify the
four `packages/schemas` commits (the friction row). No questions for the owner.
