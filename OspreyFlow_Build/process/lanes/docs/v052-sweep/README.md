# docs · v052-sweep, part one: the guides and both websites against the ADR-148 audit

The docs lane, 13 November 2026. The orchestrator brought route step 5 forward at the owner's word. Every wording
change that does not depend on search is drafted now; Tue 24 Nov's sweep is then search and OpenSearch alone.

**Sources:**
- `process/lanes/AUDIT_ADR148_2026-11-13.md`, the audit;
- `process/lanes/RULINGS_SINCE_1NOV.md` ("#n" below is its table's row);
- the code on main at d0ff521, which decides each claim.

**Scope.** The four guides (`OspreyFlow_Core/docs/`) and the two websites. **Not the client page**, which is the
owner's. Search and OpenSearch wording are left as they are today.

**Lands in:**
- **v0.5.1 notes** means the words are true of v0.5.1 as it is cut on Tue 17 Nov. They are applied to the guides on
  this branch (`lane/docs-v052-sweep`), and their gist is drafted below for v0.5.1's release notes.
- **v0.5.2** means the words describe a fix v0.5.2 brings. They are drafted below, to be applied when that fix
  lands, and not before, since the guides describe what is built.

Nothing here merges before v0.5.1's candidate is cut.

## Applied on this branch (true of v0.5.1): lands in v0.5.1's notes

| # | Where | What the guide said, or left out | Now | Source | Test |
| --- | --- | --- | --- | --- | --- |
| 1 | AG §6a.7 | "Not available on Entra yet: a scheduled run acting as its owner" | **Nothing acts as its owner on Entra yet, so loads are started by hand.** Each case is named as built: a pipeline's schedule and watched folder; *Run now* in Operations; `ospreyflow run`; a scheduled rule; the daily check for lapsing KYC documents; a list's refresh schedule; a watch's runs; anyone else's rules, hotlists and watches at a load. A load started by hand in the Studio, and *Refresh now*, are not affected | Audit 1; #46; principal_auth/__init__.py:1043-1050; scheduler.py:622-627; monitor_schedule.py:92-97; recipe_run.py:514-524; kyc_sweep.py:103-115; app.py:13769-13784 | `test_section_6a7_quotes…`, `test_entra_owner_resolution_is_refused…` |
| 2 | AG §6a.7, §6a.10 | "until then such a run is marked stopped" | Struck as untrue. A scheduled pipeline run is refused at every slot in the scheduler's words, "the identity provider could not be reached to act as the schedule's owner". Those words read as an outage, which is not what happened. Such a refusal never counts toward the three that pause a schedule (`about_the_owner=False`). A watch is retried each minute and does nothing | scheduler.py:622-627; monitor_schedule.py:92-97 | `test_no_guide_says_an_entra_scheduled_run_is_marked_stopped` |
| 3 | AG §8 (`ospreyflow run`), §9.5, §9.11; DG §6.3; UG §7.5, §7.11 | Each described running as its owner, with no word that it stops on Entra ID | Each says so, and points to AG §6a.7 | as 1 | `test_every_owner_run_says_it_stops_on_entra` |
| 4 | AG §9 | Invite, access, reset, remove and join described for every deployment | *People and roles* on Entra ID: roles, add by object id, disable; each refusal in its own words; no administrator's fallback for a missing clearance or unit; people shown by object id | #48, #49, #51; entra_people.py:118-121, 418-455 | `test_section_9_quotes_each_entra_people_refusal` |
| 5 | AG §6a.8 | Left out how long RDS can be restored to a point in time | "RDS keeps its point-in-time restore for 7 days … against the sets' 35": only a set from the last 7 days can be restored with its database | Audit 4; #26; terraform.py:191 | `test_section_6a8_gives_rds_point_in_time_restore_its_rendered_days` |
| 6 | AG §6a.5 | Left out what S3 and Athena reads cannot do | One read takes at most 1,000 objects, refused whole past it; no SSE-KMS bucket (no `kms:Decrypt` on the role); Athena's default catalog alone. VPC endpoints are left out: #54 is inferred there, and the code does not settle it | #54; s3_connector.py:57-58, 169-177; terraform.py:635-660; connector_reads.py:512-523 | `test_section_6a5_gives_one_s3_reads_cap…` |
| 7 | AG §6a.11 | Question 11 named the two registrations without saying they are two | "They are two registrations, `client_id` and `api_client_id`, not one" | Audit 5 (Am 8 p7) | none (the settings' own two keys are held by `test_admin_guide.py`'s appendix check) |
| 8 | AG §6a.11 | Volume encryption not asked | New question 12: whether `gp2-expand` encrypts its volumes; the render does not check | Audit "d5" | none |
| 9 | AG §10a | Admin › Maps' providers described for every deployment | On a shared platform, a proxied provider added in Admin has no way out until declared in `osprey.yaml` and rendered; *Build the basemap* is not available there | Audit "d7"; #25; AG §6a.5's egress rows | none |
| 10 | ArchG §1 | The identity provider is Keycloak | "…on a shared platform, the organisation's Entra ID in its place" | ADR-148 Am 8 | none |

Every guide carries its new version row (AG 1.94, DG 1.34, UG 1.51, ArchG 1.3). Each PDF is made by the orchestrator at
merge, as before: `test_docs_pdf` fails until then.

## Checked, and already right in the guides (no change)

| Claim | Where it is already right | Source |
| --- | --- | --- |
| Two Entra app registrations, the Glass's and the API's | AG §6a.1 example, §6a.7 settings, Appendix A (`client_id`, `api_client_id`) | Audit 5 (Am 8 p7). The client page says one; the page is the owner's |
| One copy of each store in the poc shape | AG §6a.1 ("one copy of each store"), §6a.2 (development copies all 1) | #62 |
| Laurium its own pod and image, reached by no screen | AG §6a.1, §6a.2, §6a.4, §10.1 | Audit 2; #31, #40 |
| The decommission keeps the backups bucket and key for their retention | AG §6a.1 (the runbooks) | #38. True of v0.5.1; v0.5.2 changes it (D3 below) |
| The shared volume is not backed up | AG §6a.8 | Audit 4; #30 |
| Roles never read from Entra groups; guests refused; overage refused | AG §6a.7 | #45, #50 |
| The managed networks are the whole shared /16 | AG §6a.5, "Narrow the managed networks" | #24 |
| `bi.` and reporting not on this profile | AG §6a.1, §6a.5, §6a.7 | #47 (v0.5.2 brings them: D4) |
| ModSecurity's body limit | AG §6a.11 question 1 | Audit "i12" |
| Bedrock inference profiles refused; the client's gateway by IAM role refused | AG §6a.9 | #32, #33 |
| Production-shape restore refused | AG §6a.8 | #43 |
| Upgrade and volume-expansion runbooks deferred | AG §6a.10 | #60 |
| Extraction engine at set-up, Admin read-only | AG §10.1 | #39 |
| Search and OpenSearch wording | left as today, for Tue 24's sweep | ROUTE_052 step 5 |

## For v0.5.1's release notes (the CHANGELOG is the orchestrator's): a draft

> **On the shared-platform profile (`cloud-platform`), with Entra ID sign-in**, nothing can act as a person who is
> not present. So loads are started by hand in the Ingest Studio: a pipeline's schedule and watched folder, *Run now*
> in Operations and `ospreyflow run` are refused, and so are a scheduled rule, the daily check for lapsing KYC documents, a screening
> list's refresh schedule and a watch's runs. A load judges only its own starter's rules, hotlists and watches. The
> scheduled runs' refusals read "the identity provider could not be reached…", although Entra may be answering, and
> they never pause the schedule. *People and roles* gives roles, adds people by object id and disables them;
> clearance, unit and handling codes, invitations, resets and removal are Entra's. RDS keeps 7 days of
> point-in-time restore against 35 days of backup sets. One S3 read takes at most 1,000 objects; SSE-KMS buckets
> cannot be read; Athena reads its default catalog alone. A map provider the Conduit proxies must be declared in
> `osprey.yaml` and rendered. Reporting (Superset) is not on this profile. The administration guide's §6a has the
> whole of it.

## Drafted for v0.5.2: apply when each fix lands, not before

**D1 · Owner resolution on Entra (audit ruling 1).** When it lands:
- Replace AG §6a.7's paragraph "Nothing acts as its owner on Entra yet…" with the fix as built: how an owner is acted
  as on Entra, and what still refuses (a disabled person, a lost right, a clearance over 24 hours old: §6a.7's
  existing rule).
- Strike the Entra sentences added in AG §8, §9.5 and §9.11, DG §6.3 and UG §7.5 and §7.11.
- Strike AG §6a.10's "anything that runs as its owner".
- Invert `test_every_owner_run_says_it_stops_on_entra`, so no guide says it stops, and keep its planted red.
- Draft the scheduler's refusal words for when an owner cannot be resolved for another reason. The building lane
  owns those words.
- Release notes: "Scheduled and triggered loads, scheduled rules, list refreshes, the daily KYC check and watches run on
  Entra ID".

**D2 and D3 · Data safety and the decommission (audit ruling 3), now designed.** These are ADR-148 Amendment 13
(lane/platform-v052-datasafety, 89816c8), as platform gave them on 13 Nov. The wording is quoted from the rendered
`INSTALL.md`, `DECOMMISSION.md` and `deploy/RUNBOOK.md` as they merge, never from the message. When they merge:
- **§6a.8's backup set:** ArcadeDB, ClickHouse, the Ingest claim, and three folders of the shared claim (the published
  pipelines, i.e. the recipes repository; the model settings; the map settings with the map key file), backed up
  read-only and put back by the claims restore. The tiles and upload scratch stay out (made again, or Ingest's).
  "The shared volume … is not backed up" is replaced by that.
- **§6a.8's point in time:** RDS keeps point-in-time recovery for 35 days in every shape, the sets' own expiry, so
  every kept set can be paired. The v0.5.1 sentence "RDS keeps its point-in-time restore for 7 days … against the
  sets' 35" becomes that. `test_section_6a8_gives_rds_point_in_time_restore_its_rendered_days` reads the rendered
  number and turns red until the sentence changes: the right signal.
- **§6a.1's decommission:** no default for the backups. Step 7 refuses until `BACKUPS=keep` or `BACKUPS=destroy`.
  - keep: the agreed `BACKUP_RETENTION_DAYS` on the bucket, the sets readable, step 9 removes them at its end.
  - destroy: every set gone now, the bucket emptied and removed, the key's deletion scheduled for 30 days and
    cancellable with `aws kms cancel-key-deletion`.
  - Step 8's check records `backups: kept (the operator chose keep)` or `backups: destroyed (the operator chose
    destroy)`.
  "the backups kept for their retention" is replaced by that.
- **Tests:** a test holding the step-8 words to `harness/cloud_platform/runbooks.py` (or wherever they merge), red first.

**D8 · OpenSearch on the poc shape (Tue 24's sweep, with search; Amendment 13).** Replace every §6a line saying the poc
makes no OpenSearch domain (§6a.1 "It makes no OpenSearch domain, and refuses…"; §6a.3 `opensearch.tf` "The standard
shape alone"; §6a.1 "no pod is given its address yet"). Use the merged facts:
- every shape has its own domain: OpenSearch 2.17, two `t3.medium.search` data nodes of 50 GiB in two zones, in the
  VPC on 443, TLS 1.2, encrypted at rest and node to node;
- each request signed (SigV4) by the namespace's IRSA role, the access policy admitting that role alone, no
  fine-grained access control (no OpenSearch user or password), dataset access in OspreyFlow's own queries;
- `opensearch_signing: none` for a platform whose module puts a signing proxy in front;
- the client provides two private subnets in two zones, and egress to the domain, and is asked about an IAM-only
  policy (a new §6a.11 question);
- no index backup: a restore ends with the rebuild and then the drift check, each from a standing suspended CronJob
  (`ospreyflow-search-rebuild`, `ospreyflow-search-drift`), quoted with their healthy last lines from the RUNBOOK;
- the domain goes with the namespace's Terraform at decommission, its index not kept.

**D4 · Superset and report sync on Entra (ROUTE_052 scope; #47).**
- Strike AG §6a.1's "Reporting is not rendered" paragraph, and replace it with what is rendered: Superset and the
  report sync, one copy each in poc and development and two in production, signing in through Entra ID.
- AG §6a.5: the `bi.` name returns. Add its certificate (audit "i5") to §6a.11's question 4.
- AG §6a.7: strike "Reporting is not available either…".
- AG §6a.8: the runbook's note that `deployment/report-sync` "is not rendered" goes.
- AG §6a.10: strike reporting.
- AG §9's dashboard-identity refusal ("Dashboard identities are not registered on this deployment yet.") goes, if the
  fix registers them. `test_section_9_quotes_each_entra_people_refusal` follows the code, and turns red until the
  sentence goes.
- §12, Dashboards: the cloud-platform sign-in.

**D5 · The manifest is the one source (ROUTE_052, rules for every lane).** AG §6a.2's component table and §6a.1's
connection counts are hand-kept copies of what the manifest will hold.
- Replace each with the output of the command that prints the client page's tables from the manifest, under its own
  name.
- Add a test that the guide's tables are that command's output, red first against a planted difference.
- The ingest image (#62, "no ingest image") is settled there. The guides name no ingest pod today.

**D6 · Entra people, if the owner rules audit 4b, 4c and 4d in.**
- 4b, guests: AG §6a.7's guest refusal becomes the setting that admits them.
- 4c, the fallback: §9's "No administrator can give a missing clearance or unit instead" becomes the fallback as
  built.
- 4d, roles from groups: "Roles are not read from an Entra token" gains the group table.

None is drafted further until ruled.

**D7 · Acceptance (audit ruling 5; #61).** No guide claims spec 08 was run. When step 6 runs it, AG §6a.1's "Both
were run on a kind cluster (R1, 13 November 2026)" gains the scenarios run and against what.

## The websites: apply with the v0.5.1 re-check, on sites2's `build.py`

The sites as merged and as on `lane/docs-sites2` claim nothing about Entra, schedules, backups or reporting on the
shared platform, beyond the Features page's *On main, coming* section. That section is re-checked against v0.5.1 by
the `CHECKED_AGAINST` step once v0.5.1's CHANGELOG lands. These lines go in then, on `lane/docs-sites2`'s `build.py`
(this branch is from main, so editing the sites here would conflict with it):

| Line | Becomes | Source |
| --- | --- | --- |
| "A profile for shared government Kubernetes platforms: one namespace, … a single-copy shape for a proof of concept. Not yet installed on a platform." | adds: "People sign in with the organisation's Entra ID. Scheduled and triggered loads, and reporting, are not yet available there." | Audit 1; #46, #47 |
| "A second, open-source extraction engine for structured facts in documents." | adds: "It runs beside the Conduit; no screen reaches it yet." Laurium stays unnamed | Audit 2; #40 |
| "Routing to your organisation's own AI gateway, or to Amazon Bedrock in London, on the shared-platform profile." | "…your organisation's own AI gateway, by its token, or to Amazon Bedrock's on-demand models in London…" | #32, #33 |

The overview's chapters (`overview.py`) were checked against main on 13 Nov. None claims a shared-platform behaviour
that the audit contradicts. Its Vault chip "OpenSearch or PostgreSQL" is search wording, left for Tue 24.
