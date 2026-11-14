# docs lane · the sites step, ospreyflow.org and ospreyflow.net · 12 November 2026

Branch `lane/docs-sites` from main 5a8c2d8, on the Mac, no server, no stack. Nothing published, pushed or created; the
current six-page site and `publish_pages.sh` unchanged. Head: see `git log`. Nothing running.

| Item | State | Proof |
| --- | --- | --- |
| 1. The two sites beside the current one; build.py kept (accepted, conditions a–c) | Done: the drafts committed as delivered (8fecd8d, their HTML build.py's byte for byte), then build.py writing `sites/org/` and `sites/net/`, `--out`, images only with `--images` | `test_the_pages_are_build_pys_output`, red on a one-space drift |
| 2. Every page held to the rules, red first | Done: 12 checks, each with planted cases in build.py's shapes; red on the drafts for Laurium, the placeholders, the old statement, an install without `--mode`, and the build | `tests/test_sites.py` (56 cases); `gates/sites-red-first.txt` |
| No client named, by hash (the orchestrator's design) | Built against a synthetic entry; `client_hashes.py` for the owner, a count printed, never a name | `test_the_client_check_*`, `test_the_script_appends_hashes_and_prints_no_name` |
| 3. Every claim on Features, Get started and UK public sector checked against v0.5.0 (4b8de6c) and main | Done; listed below. Each page says what is in v0.5.0; Features heads what is only on main | the guides and code, file and line in the fact-check (this session) |
| 4. and 5. Proposals for the owner | Applied on 14 November 2026 at the owner's word: `marketing_site/identifier_check.py` and `TEAM_NAMES` (4), `publish_pages.sh --site org\|net` and `sites/REPOSITORIES` (5), the proposal folder removed | `tests/test_site_identifiers.py` (21; `gates/sites-identifier-red-first.txt`: 19 of 21 red against the old rule), `tests/test_publish_pages.py` (14; `gates/sites-publish-red-first.txt`) |
| 6. Screenshots | Waits for the demo's freeze after Friday | — |
| 7. The current site once these are live | Proposed: four redirect pages, the repository's website field, Pages off after six months | `sites/README.md` |
| Review | One lane-reviewer round, 8 must-fix items and 6 minor, fixed except as said below | — |

**Item 3, what changed** (all true in v0.5.0 unless said):
- Sign-in through Entra ID, ADFS or another OpenID Connect provider on a server of your own alone; elsewhere OspreyFlow's own accounts (`cli/ospreyflow/answers.py` 368–377; admin guide §5a.1).
- An update backed up first and rolled back on failure only on one computer or a server of your own, installed from a release; Enterprise by installing the new release (admin guide §14's table; `harness/update.py`). Signed releases kept (true).
- The public-sector install command given its `--mode lite` (without it the install refuses: `cli/ospreyflow/main.py` 722); a test now holds every install command shown to its mode.
- The Vault: DuckDB or ClickHouse for analytics, OpenSearch or PostgreSQL for search, S3-compatible storage or Azure Blob (admin guide 132, 2939).
- Connection strength is count and recency, rarity shown beside it; the map's boundary filters; the timeline dims; the Matrix gives strength and rarity (user guide §5.3, §5.4, §5.11, §5.12).
- The UN and OpenSanctions lists synthetic until their licences are confirmed; a list is re-screened when one you load changes (admin guide §9.5).
- A second person for a high-severity close; a whole-deployment rule removed (v0.5.0 cannot make one).
- Drawn items' source: a note, a document or both. Pipelines: each source with its own profile, mapping and load. Loaded data reaches a dataset only through a published pipeline.
- Get started: Blank loads no demonstration data; four guides, the Architecture Guide added; Small's needs (Git, uv; amd64, Python 3.12, port 443, access to the releases).
- UK public sector: the GOV.UK look "to be used" for gov.uk services (stated, not enforced); calling out says what the install and a server fetch; accessibility scans "on every screen we test, in light and dark, under GOV.UK on most".
- Features' last section headed "On main, coming with the next release": the shared-platform profile (not yet installed on a platform), S3 and Athena, the owner's extraction-engine line, the model route on that profile. The change-log pointer dropped (its Unreleased section is empty).
- Beyond the three pages, the same claims on .net and Home; Contribute's checks, sign-off, guide count and scans; .net's "air-gapped" claim struck; nothing promised "with the next release".
- The map and Verify images were swapped in the drafts (each showed the other's screen): swapped back.

**The owner's four decisions, applied as given:** (1) Couldridge, in the Team page and TEAM_NAMES; (2) servicecentre@solirius.com
on .net's Contact and .org's Contribute, with "Put 'OspreyFlow security' in the subject", and the checklist line;
(3) "How it is built" unchanged; (4) Laurium not named, "a second, open-source extraction engine for structured facts in
documents", with a test.

**For the owner:**
1. **A hash is not a secret.** Anyone can hash a list of UK forces and departments and see which are in `client_names.sha256`.
   Keep the file out of git, use a keyed hash, or accept it, before a real name is added (README says so).
2. **The extraction engine line** is yours verbatim. On main it runs on the shared-platform profile alone and no screen reaches
   it; the next line says "on the shared-platform profile", this one does not. Add the qualifier or keep it.
3. **Contribute's process**: "Before it is merged, the project's checks run on it" describes practice, not code: the public
   repository runs no workflow on a pull request. Confirm or strike.
4. **The images** predate v0.5.0 (the old brand, tabs and Inspector fields); the Features page says so until item 6.

**Not done:** item 6; the client names' red run (the owner's session); item 5's run against real repositories.
**Carried, minor:** `build.py`'s `SHOTS` holds six entries no page shows, kept for item 6's captures.

---

# docs lane · D2c part 4, the model route on the `cloud-platform` profile (administration guide §6a.9) · 12 November 2026

Branch `lane/docs-d2c4` fresh from main 5bc60ba. No HANDOFF.md, no earlier commits: the brief was untouched. Head: see `git log`. Nothing running.

| Item | State | Proof (OspreyFlow_Core unless named) |
| --- | --- | --- |
| The gateway, always rendered; the Conduit and Laurium call it | Done (§6a.9) | `harness/cloud_platform/profile.yaml` 70, 80–90 (`paths`); ADR-135 Am 8 d1 |
| Three kinds; gateway by `openai/`, Bedrock by `bedrock/`; `auth` and `region` defaults; this profile's alone | Done | `packages/schemas/deployment.py` 303, 310, 457–459, 473–477, 480–484 |
| London only; a model's own id; no inference profile, no ARN | Done | `deployment.py` 324, 587–596 |
| The refusals in words | Done | `deployment.py` 487–507 (address), 542–622 (`engine_refusal`) |
| `gateway.tf`: policy, role, trust, attachment, service account; only with a Bedrock engine | Done | `harness/cloud_platform/terraform.py` 550–553, 852–958; `__init__.py` 297–310, 1010–1013; `settings.py` 109–126; `platforms/client.yaml` 55 |
| The egress: the gateway's own policy, engine hosts, STS always, a provider with no known host refused | Done | `profile.yaml` 38, 43–50, 59, 65, 70; `__init__.py` 497–525, 570, 610–616; `deploy/helm/ospreyflow/templates/networkpolicies.yaml` 93, 119–121, 205 |
| Admin › Models: the refusal's exact words (name in brackets; the role clause for Bedrock alone), key and limits refused, *not made by the render* | Done | `services/api/model_admin.py` 188–236, 825–841, 1226–1234, 1264–1269, 1285 |
| Bedrock: no key; key state "IAM role: no key kept"; no Enter or Remove key on screen; 409 from the API | Done | `apps/workspace/src/admin/sections/Models.tsx` 45, 424, 432; `model_admin.py` 1233, 1268 |
| *Test the connection*'s words, per kind | Done (summarised) | `model_admin.py` 696–740 |
| The order for a newly declared Bedrock engine: Terraform before the values | Done in §6a.9 and §10.1: the chart makes no gateway ServiceAccount (only `backups.yaml` 69 has one), so `helm upgrade` first leaves the gateway's pod unschedulable. **This departs from the brief's order: for the orchestrator's ruling** | `__init__.py` 1010–1013; `terraform.py` 944–958 |
| An engine removed in Admin keeps its host while `osprey.yaml` declares it (§6a.5 and §6a.9 corrected) | Done | `__init__.py` 512–525 (`config.models.enabled_providers`) |
| Laurium's key | Cross-referenced to §6a.1 | — |
| Not yet tried | Said as such: no real Bedrock call, STS's regional endpoint, model access, Bedrock's undocumented words, the client's gateway, the gateway by the role | ADR-135 Am 7 d5, Am 8 "Not done" |
| *Coming* | Held nothing of the model route; nothing struck | — |
| Example `osprey.yaml` | Valid on cloud-platform, both engines refused on Small, through `ModelsConfig` and `engine_refusal` | run on the Mac, this session |
| Review | One lane-reviewer round, 13 findings (five must-fix), all fixed | — |
| Docs gates | `test_admin_guide` green; `test_docs_pdf` red for the admin PDF alone, made at merge | `gates/d2c4-docs-tests.txt` |

**For the orchestrator (rule 11, spec gaps in the ADR, not docs' to amend):** ADR-135 Amendment 8 decision 3 says "the Calico policy
selects every pod (`all()`), so the hosts are the namespace's, not the gateway's alone", stale since ADR-148 Amendment 5 point 21
(the engine hosts are in `default.ospreyflow-egress-litellm` alone); and "an engine disabled in *Admin › Models* keeps its host open
until the next render", whereas the next render opens it again while `osprey.yaml` declares it. The guide says what the code does.
Separately: for a newly declared Bedrock engine, the refusal's own words ("Declare it in osprey.yaml, re-render, and have the
platform team apply the Terraform") give the right order, but §10.1's general order (values before Terraform) does not hold for it.

---

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
| Server gates at 0878e2a (on main 8bb7f7b, after the orchestrator's review) | `make -k ci` green; `make test`: the GPU case and `test_docs_pdf` (expected), and test-js's first-frame budget and a hook timeout under load 44–71, main 0ac0abc failing the same budget alone; `make live-collect` green | `gates/0878e2a.{ci,test,live-collect}.txt` |

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
