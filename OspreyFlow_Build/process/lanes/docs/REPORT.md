# docs lane · D2c part 2, Entra ID's sign-in (administration guide §6a.7) · 11 November 2026

Branch `lane/docs-d2c` rebased onto main; built at 2f21e72, P11 part 2's alignment eed9465, the review's fixes 16f78b5 (head: see `git log`). Nothing running.

| Item | State | Proof |
| --- | --- | --- |
| Entra ID's claims (brief: "after P10") | Done for P10 part 1: §6a.7, 1.79–1.81, spec 10 word for word | Each sentence against `packages/principal_auth` and `test_auth_entra_claims.py`; lane-reviewer, one round, fixed |
| The profile's side (settings in `osprey.yaml`, the Conduit passing them, Keycloak not rendered, *Admin › People*'s roles by tenant and `oid`, no scheduled run as owner or Superset roles on Entra) | *Coming* in §6a.8 (P10 part 2) | Amendment 6's "Carried to part 2"; MORNING 37's ruling |
| P11 part 2's gateway in §6a (the orchestrator's addition) | Done, 1.80–1.81 | Render of the three synthetic deployments (development 3.95 CPU, 27.1 GiB, limits 33.75 GiB) |
| Backups and restore (P9), runbooks (P9b), Laurium (P12 part 2), L1.9 part 2, P8, P7b's rulings | Untouched, waiting | Not merged |
| Docs gates and `test_docs_pdf` | Green on the Mac | `gates/d2c-p2-docs-tests.txt` (336 passed; 1 failed, `botocore` absent from this Mac's venv) |

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
