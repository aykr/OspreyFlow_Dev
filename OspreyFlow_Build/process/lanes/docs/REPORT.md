# docs lane · D2c part 3, §6a as main holds it after P7b, L1.9 part 2, P9, P12 part 2 and P10 part 2 · 12 November 2026

Branch `lane/docs-d2c` fresh from main e59da4f (the orchestrator named 33e402d; main had moved on, docs files unchanged). Head: see `git log`. Nothing running.

| Item | State | Proof |
| --- | --- | --- |
| P10 part 2 for §6a: reporting not rendered, refused at render, in its words | Done (§6a.1, §6a.5, §6a.9) | `harness/cloud_platform/__init__.py` 173–180 |
| P7b: the secrets table and the one allow-egress | Done: each workload's keys, service account, egress and ingress (§6a.3, §6a.5); the poc shape, the ceiling, the runbooks, the decommission check, five fixtures (§6a.1, §6a.6) | ADR-148 Am 5; profile.yaml; networkpolicies.yaml |
| P12 part 2: §10.1's read-only extraction row and how to change the engine | Done | `Models.tsx` 349–354; ADR-135 Am 9 point 5 |
| L1.9 part 2: `connector_sources`, its refusals, `connector_sources.tf`, connector hosts to the Conduit alone | Done (§6a.3, §6a.5) | ADR-140 Am 21; `connector_reads.py` |
| Backups and restore after P9, from RUNBOOK.md as built; P9b's runbooks *coming* | Done (§6a.8, §6a.9) | ADR-148 Am 7; `deploy/RUNBOOK.md` |
| Where Laurium runs | Done (§6a.1): its own pod `laurium`, image `ospreyflow/laurium`, repository in the namespace's registry, port 8000 | ADR-142 Am 8 d9; `harness/laurium.py`; the dry-run push in `gates/d2c-p3-guide-commands.txt` |
| §6a.7 against P10 part 2's code | Corrected: `token_version`, `api_id_uri`, `claims_mapping_policy`, the derived issuer, audience and keys, the guest check by `idp`'s tenant | `deployment.py` 1162–1182; `site.py` 353–361 |
| The guide's commands | Unpinned render and dry-run push run as written, exit 0 | `gates/d2c-p3-guide-commands.txt` |
| Totals | From renders of the fixtures | §6a.2's table; the reviewer recomputed them |
| Review | One lane-reviewer round, eight must-fix items, all fixed | — |
| Docs gates; `test_docs_pdf` | Gates green; `test_docs_pdf` red until the orchestrator makes the PDF at merge, as asked | `gates/d2c-p3-docs-tests.txt` |
| Server gates at c4f149c | `make -k ci`: test-file-coverage-check (known) and harness-a11y (load timeouts; passed 34 of 34 alone, as main did); `make test`: the four known (GPU, release_local_matrix, test-file-coverage, entra_people_live's 19 errors) and `test_docs_pdf` (expected); `make live-collect` green | `gates/c4f149c.{ci,test,live-collect}.txt` |

**For the owner: the page shared with the client** (ADR-142 Amendment 8 decision 9) shows Laurium inside the Conduit and
the Workers. What is true, to correct it:
1. Laurium is its own pod (`laurium`), from its own image (`ospreyflow/laurium`, built from `services/laurium/`) in its own
   repository in the namespace's registry, on port 8000; neither inside the Conduit nor inside the Workers.
2. The Conduit alone calls it; the Workers never do.
3. It reaches nothing but the model gateway, with a key of its own scoped to its models; the gateway's master key never
   enters its pod; it holds no service account, no token and none of our Secret.
4. It serves the review queue's document extraction alone, and no screen reaches it yet; Questions, Ask, email and a
   document's content stay on Deep read.
5. It is the `cloud-platform` profile's preset, and that profile's alone.
6. It has read a real model's answer only outside the rendered route; it is to be shown on the client's own engine at
   the install.

**For other lanes (code, not docs):**
- Platform/admin: `INSTALL.md` step 6 (`runbooks.py` 180–190) renders and restarts without `helm upgrade`, so a new
  `first_administrators` never reaches the ConfigMap; the guide says so.
- Platform-b and case-b: *Admin › Models*' engine refusal and its extraction-engine row leave out installing the values.
- Platform: a `mail:` section still needs its host's networks and its password in the Terraform though no pod reaches it.
- Case: RUNBOOK.md 219 and 234 scale `deployment/report-sync`, not rendered on this profile, and scale back to 1 even in
  production. `harness/laurium.py` 19–22's docstring says the egress is not yet held; P7b's row is in.
- Orchestrator: `progress.tsv` 86 says P7b's runbooks were "each run on kind"; ADR-148 Am 5 says no block has run on a cluster.
- Platform/admin: the reporting refusal's words name a build step, "P10" (`harness/cloud_platform/__init__.py` 178), in a
  message an operator reads.
- The orchestrator's review (relayed on sol): three should-fixes and eight notes, each applied in the 1.86 text; the
  orchestrator records the seven items above in CARRIES.

**Waits:** P9b (the backups' alert, volume expansion, the upgrade runbook, the production restore), P8 (the shared folders),
reporting and owner resolution on Entra, a screen for Laurium, one real Entra token.

---

# docs lane · D2c part 2, Entra ID's sign-in (administration guide §6a.7) · 11 November 2026

Branch `lane/docs-d2c` rebased onto main; built at 2f21e72, P11 part 2's alignment eed9465, the review's fixes 16f78b5 (head: see `git log`). Nothing running.

| Item | State | Proof |
| --- | --- | --- |
| Entra ID's claims (brief: "after P10") | Done for P10 part 1: §6a.7, 1.79–1.81, spec 10 word for word | Each sentence against `packages/principal_auth` and `test_auth_entra_claims.py`; lane-reviewer, one round, fixed |
| The profile's side (settings in `osprey.yaml`, the Conduit passing them, Keycloak not rendered, *Admin › People*'s roles by tenant and `oid`, no scheduled run as owner or Superset roles on Entra) | *Coming* in §6a.8 (P10 part 2) | Amendment 6's "Carried to part 2"; MORNING 37's ruling |
| P11 part 2's gateway in §6a (the orchestrator's addition) | Done, 1.80–1.81 | Render of the three synthetic deployments (development 3.95 CPU, 27.1 GiB, limits 33.75 GiB) |
| Backups and restore (P9), runbooks (P9b), Laurium (P12 part 2), L1.9 part 2, P8, P7b's rulings | Untouched, waiting | Not merged |
| Docs gates and `test_docs_pdf` | Green on the Mac | `gates/d2c-p2-docs-tests.txt` (336 passed; 1 failed, `botocore` absent from this Mac's venv) |
| Server gates at 77b249e | `make -k ci` green; `make test` 1 failed (the server's GPU), 11871 passed | `gates/77b249e.{ci,test}.txt` |

- **For platform-b (code, ADR-135 Am 8):** *Admin › Models*' refusal says "re-render, and have the platform team apply the
  Terraform" but an engine's way out also needs the new values installed (`helm upgrade`): the egress and `OSPREY_MODEL_ROUTES_MADE`
  live in `values.yaml`. The guide says so and calls the words a known issue.
- **For admin (P10 part 2):** Entra's sign-in endpoints in the egress list are decided nowhere yet (struck from §6a.8 for that reason);
  the Conduit fetches Entra's signing keys, so its host must be allowed out. Amendment 6 omits `sub`, which an Entra token must carry.
- **Not traceable to a merged record:** §6a.8's "first administrator named by `oid` in the settings" comes from the orchestrator's
  ruling (MORNING 37), the owner's to overrule; Amendment 8 is reserved.

---

# docs lane · D2c part 1, the `cloud-platform` profile (administration guide §6a) · 11 November 2026

Branch `lane/docs-d2c` on main 5a554e3: b24380c (built), then the two reviews' fixes (head: see `git log`). Nothing running.
- **Every sentence traceable, unbuilt marked *coming*: met.** §6a 1.76 (spec 10 word for word) written from ADR-148 Am 1–2,
  `harness/cloud_platform/`, `harness/cluster.py`'s blanks, `cli/ospreyflow/images.py` and a render of the guide's own example.
- **Commands run: met for those that need no Docker** (`gates/d2c-p1-guide-commands.txt`: every §6a line, extracted from the
  guide and run verbatim at its commit, with its exit code). Helm install, tofu, the push and cp-policy-check (Docker, Helm's
  image) are unrun until P7b's kind run, as the guide says.
- **Docs gates and `test_docs_pdf`: met** (`gates/d2c-p1-docs-tests.txt`: 201 passed, four gates green). The admin PDF alone remade.
- **Version rows:** 1.74 (part 1), 1.75 (the reviews' fixes), 1.76 (the re-check). Friction row `friction/2026-11-11-docs-d2c-cloud-platform.md`.
- **Decision taken:** §6a of the administration guide, not a standalone guide (that needs `tools/docs_pdf.py` and `doc_site.py`,
  not docs' files). The owner may overrule; the section moves out whole.
- **For platform (code, P7b):** (1) the profile does not set the OFFICIAL-SENSITIVE ceiling (Am 2's carry); (2) `write()` does not
  make `terraform/`, so a first render into a new folder fails; (3) an unpinned render's plan copies third-party images by tag,
  never exercised by the tests' stand-in resolver; (4) `images.py:28-29` says `python -m harness.render`, which needs
  `PYTHONPATH=.:packages`; (5) no identity step on this profile until P10; (6) OpenSearch made, read by no pod. Each is in the
  guide as it stands.
- **Waits:** P10 (Entra ID), P9 (backups and restore), P9b (runbooks), P11 part 2, P12 part 2 (Laurium, where it runs, and the
  corrections to the page shared with the client), L1.9 part 2, P8: each *coming* in §6a.7 (§6a.8 since part 2).
- **No questions for the owner.** The installed `ospreyflow` on this Mac does not import (`httpx`); the worktree's CLI was used.
