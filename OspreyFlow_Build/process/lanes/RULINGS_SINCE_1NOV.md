# Rulings since 1 November 2026 that refused, removed, narrowed or deferred something the client page or an ADR requires

Compiled read-only on 13 Nov 2026 at the owner's request ("One list, so I am not finding these one at a time"). The
sources are 06_DECISIONS.md, MORNING.md, CARRIES.md, the lanes' REPORTs and BRIEFs, and the client page
(`Claude outputs/OspreyFlow_Prison_Network_App_PoC.html`, "PAGE").

"Never asked (listed)" means the ruling was listed in MORNING for the owner to overrule, but the owner never answered
it. By the owner's measure of 13 Nov, that is not asked. "Told and accepted" means MORNING records the owner's answer.
Anything inferred is marked so.

## Never asked and still in force, most serious first

1. **Owner resolution on Entra (#46).** Scheduled loads, Airflow-triggered runs, screening refresh, the KYC sweep, and
   other authors' rules and hotlists at load all stop on the client's profile. Audit ruling 1 fixes it in v0.5.2.
2. **Decommission keeps the backups bucket and KMS key (#38),** against the page's record of destruction. Audit
   ruling 3 fixes it in v0.5.2.
3. **Entra access (#48, #49):** no administrator fallback for unit and clearance (the page's own mitigation), and on
   Entra, Admin cannot set Access or Remove people. The fallback is audit 4c.
4. **Maps (#29, #25):** no offline basemap on the client install, and a map provider added in Admin gets no egress.
5. **Data safety (#30, #26):** the shared claim (pipelines, settings, key file) is in no backup set, and RDS
   point-in-time restore lasts 7 days against 35-day sets. Audit ruling 3 fixes both in v0.5.2.
6. **Acceptance (#61):** spec 08 has never run on the profile. Audit ruling 5 makes it step 6 of v0.5.2.
7. **Model routes (#32, #33):** Bedrock models offered in London only through inference profiles are unusable, and the
   client's gateway signed in by the IAM role is refused.
8. **Egress (#24):** the whole shared /16 is reachable from allowed pods, other tenants' stores included.
9. **Rules (#17):** pattern and AML/KYC template rules run "just for me", so they never raise case alerts.
10. **Roles (#45):** roles are never mapped from Entra groups, which the page says they are. Audit 4d.
11. **Entra people (#50, #51):** guests and federated members are refused (audit 4b), and display names show object ids.
12. **Run API leftovers (#19):** the Airflow provider package, the budget alert, the concurrency limit, and Phase 10's
    exit run.
13. **S3 and Athena (#54):** SSE-KMS buckets, VPC endpoints, and folders over 1,000 objects.
14. **Laurium (#37, #41, #39, #42):**
    - its exit was eased;
    - it is refused off cloud-platform;
    - Admin shows the engine read-only;
    - the CI image leg is not run;
    - no screen reaches it (#40, audit 2).
15. **Production-shape restore** is refused until P9b (#43).
16. **Admin › Models is gated on the render (#52),** and `connector_hosts` reach the API alone (#53).
17. **Minor:**
    - #12 and #13: the SQL-step refusal, and the missing Needs-you flag;
    - #58: trends undercount;
    - #34: ADR-110 Am 20;
    - #57: a rule screens only lists its deployer is cleared for;
    - #60: the upgrade runbook is deferred;
    - #22: `update` option A;
    - and #1–6, 11, 14–16, 18, 20–21, 27, 36, 44.

## The full table

| # | Date | Who ruled | What | Required by | Owner's knowledge | Status |
|---|---|---|---|---|---|---|
| 1 | 7 Nov | orchestrator | Rule-audit entries before L2.8b that name an alert lose their words | ADR-133/146 (inf.) | never asked (listed) | in force |
| 2 | 7 Nov | orchestrator (ADR-124 Am 17) | A jump to an alert whose evidence is not whole is refused as missing | ADR-146 (inf.) | never asked (listed) | in force |
| 3 | 7 Nov | orchestrator | A pipeline's pinned model version only recorded; Test uses the live model | ADR-140 (inf.) | never asked (listed) | in force (inf.) |
| 4 | 8 Nov | orchestrator (ADR-135 Am 3) | No model usage per person; no person id to the gateway | spec 00/04 | never asked (listed) | in force |
| 5 | 8 Nov | orchestrator | Data Engineer and Administrator bundles narrowed | ADR-112 | never asked (listed) | since built (inf.) |
| 6 | 8 Nov | rules-b | Board filtered to a rule: outcome and time-to-close panels say "(every rule)" | ADR-146 (inf.) | never asked (listed) | in force, no CARRIES row |
| 7 | 9 Nov | owner | "Who can" refusals name roles, never people | ADR-145 Am 4 d12 | owner ruled | in force |
| 8 | 9 Nov | owner | Promotion revert is an operator command only | ADR-143; PAGE:227 | owner ruled | in force |
| 9 | 9 Nov | owner (ADR-133 Am 9) | ADR-133's Lists tab retired | ADR-133 | owner ruled | done |
| 10 | 9 Nov | owner | A removed composite case's layer is never merged | ADR-143 Am 2 | owner ruled | in force |
| 11 | 9 Nov | orchestrator | Removing a gazetteer from a case deletes nothing | ADR-147 Am 2 | never asked (listed) | in force |
| 12 | 9 Nov | orchestrator | An expert SQL step that rewrites a handling-bound column is refused | ADR-140 Am 14 | never asked | in force |
| 13 | 9 Nov | orchestrator | No above-clearance proposal flag in Needs you | ADR-143 Am 4 | never asked | in force |
| 14 | 10 Nov | orchestrator (ADR-145 Am 9) | At Disable, a recipient must clear the case's highest marking | ADR-145 Am 8 | never asked (listed) | in force |
| 15 | 10 Nov | orchestrator (ADR-147 Am 3) | Six gazetteer identifiers withheld from every node | ADR-147 (inf.) | never asked (listed) | in force |
| 16 | 10 Nov | orchestrator | A new rule cannot take the whole-deployment scope | ADR-133 (inf.) | never asked (listed) | in force |
| 17 | 10 Nov | orchestrator | Pattern and AML/KYC template rules run "just for me" | ADR-133 Am 3; ADR-146 d3; PAGE:597 | never asked (listed) | in force |
| 18 | 10 Nov | orchestrator | Quota run counts shown only to administer_system | ADR-141 | never asked (listed) | in force |
| 19 | 10 Nov | studio L1.7 | Airflow provider package, Prefect/Dagster wrappers, per-pipeline zip, quotas, concurrency, trend, budget alert, Phase 10 exit run not built | ADR-141 d2,3,5,8,9; PAGE:231 | never asked | in force, no row |
| 20 | 10 Nov | orchestrator (ADR-140 Am 19) | A Join of a marked with an unmarked table refused | ADR-140 | never asked (listed) | partly built |
| 21 | 10 Nov | orchestrator | A retyped item's pictures and Same/Not-the-same decisions left out at a merge | ADR-143 Am 7 | never asked (listed) | in force |
| 22 | 10 Nov | orchestrator, option A | `update` refuses a pre-ADR-135-Am-2 deployment | ADR-114 (inf.) | never asked (inf.) | in force |
| 23 | 10 Nov | platform P7, orchestrator accepted | Shared folders on one RWO claim | ADR-148 d6 | accepted (ADR-142 Am 8 p5) | in force until P8 |
| 24 | 10 Nov | platform P7 | Egress "managed networks" is the whole shared /16 | ADR-148 d7; PAGE:445, 639 | never asked | in force |
| 25 | 10 Nov | platform P7 (left to L1.9, not done) | Egress from osprey.yaml only: map providers added in Admin get none | ADR-148 d7 | never asked | in force (model side ruled 13 Nov) |
| 26 | 10–11 Nov | P7 render, orchestrator ruling 9 | RDS point-in-time restore of 7 days against 35-day sets | ADR-148 Am 7 p10; PAGE:641 | the gap never put to the owner | in force (audit 3) |
| 27 | 10 Nov | orchestrator | No Java in the Conduit; the basemap off-platform, its upload P8's | ADR-147 Am 2 | never asked (listed) | in force |
| 28 | 11 Nov | owner accepted (ADR-142 Am 8 p4-5) | P8 deferred; P9 cut; P7a after the install | ADR-148 d6, d12, d13 | told and accepted | in force |
| 29 | 11 Nov | consequence of #28 | No offline basemap on the client install | ADR-148 d12; PAGE:255, 442 | not put to the owner (inf.) | in force |
| 30 | 11 Nov | case P9 within the cut | The shared claim in no backup set | ADR-148 d13; PAGE:622, 676 (inf.) | never asked | in force (audit 3) |
| 31 | 11 Nov | owner (ADR-135 Am 6) | Laurium its own service | PAGE:282, 290, 423, 438 | owner ruled | in force (page to correct) |
| 32 | 11 Nov | orchestrator | Bedrock geography-prefixed ids and ARNs refused (London inference profiles) | ADR-135 Am 4 d1(b); PAGE:451 | never asked (listed) | in force |
| 33 | 11 Nov | platform-b P11 | The client's gateway signed in by IAM role refused | ADR-135 Am 4 d1(a); PAGE:451 | never asked (inf.) | in force |
| 34 | 11 Nov | orchestrator (ADR-110 Am 20) | A schedule-owner fault's error text in the log only | ADR-110 Am 19 p5 | never asked (listed) | in force |
| 35 | 11 Nov | orchestrator | No OpenSearch in poc; no pod reads OpenSearch anywhere | ADR-148 d4; PAGE:441 etc. | owner ruled after the fact (13 Nov) | v0.5.2 |
| 36 | 11 Nov | orchestrator | poc ceiling defaults to OFFICIAL-SENSITIVE; HMP pack left out of poc acceptance | ADR-148 Consequences | never asked (listed) | in force |
| 37 | 11 Nov | orchestrator | Laurium's exit eased; the client's engine moved to the install | ADR-135 Am 6 | never asked (listed) | in force |
| 38 | 11 Nov | orchestrator | Decommission keeps the backups bucket and KMS key by default | PAGE:686, 692 | never asked (listed) | in force (audit 3) |
| 39 | 11 Nov | orchestrator | Extraction engine at set-up only; Admin read-only | ADR-135 Am 5 d2 | never asked (listed) | in force |
| 40 | 11 Nov | orchestrator on case-b's recommendation | Laurium serves the review queue only; no screen calls it | ADR-135 Am 5 d4; PAGE:193, 228, 235-238 | partly accepted | in force (audit 2) |
| 41 | 11 Nov | case-b | Laurium refused on every profile but cloud-platform | ADR-135 Am 5 d2 | never asked | in force |
| 42 | 11 Nov | case-b | `no_langchain_check`'s image leg not in CI | ADR-135 Am 6 d1 | never asked | in force |
| 43 | 11 Nov | orchestrator | Restore refused for the production shape until P9b | ADR-148 d13 | never asked (listed) | in force |
| 44 | 11 Nov | orchestrator ruling A | ClickHouse's user may RESTORE 35 days of deleted rows | ADR-148 d13 (inf.) | never asked (listed) | in force |
| 45 | 11 Nov | orchestrator | Roles never mapped from Entra groups | PAGE:631 | never asked (listed) | in force (audit 4d) |
| 46 | 11 Nov | orchestrator | Owner resolution unavailable on Entra | PAGE:231; ADR-110; ADR-141 Am 1 p3 | never asked (listed) | in force (audit 1) |
| 47 | 11 Nov | orchestrator ruling (a) | Superset and report sync not on cloud-platform | PAGE:111, 205, 322-327, 419 … | owner ruled after the fact | v0.5.2 |
| 48 | 11 Nov | admin P10 | On Entra: invite, reset, Access, Remove, Join and dashboard identity refused | ADR-112 Am 3; ADR-111 d7; PAGE:711 | never asked | in force (identity: v0.5.2) |
| 49 | 9–11 Nov | orchestrator's P10 plan, admin | Missing clearance or unit refused; no administrator fallback | PAGE:711 | never asked | in force (audit 4c) |
| 50 | 11 Nov | admin | Guest and federated members refused | PAGE:448 (inf.) | never asked | in force (audit 4b) |
| 51 | 11 Nov | admin | Display names show object ids on Entra | ADR-106 | never asked | in force |
| 52 | 11 Nov | orchestrator | Admin › Models enables only engines the render made | ADR-135 Am 2 | never asked | in force |
| 53 | 11 Nov | orchestrator's addition (a) | `connector_hosts` reached by the API alone | ADR-148 Am 5 p21 | never asked | in force |
| 54 | 11 Nov | studio-b L1.9, orchestrator | SSE-KMS, VPC endpoints, S3 folder > 1,000 objects, Athena default catalog only | PAGE:180, 443, 632 (inf.) | never asked | in force |
| 55 | 12 Nov | orchestrator | 24-hour clearance freshness; first-admin re-grant rule | ADR-145 Am 8 | told and accepted | in force |
| 56 | 12 Nov | owner | A close decides only the citations the closer can read | ADR-109 | owner ruled | in force |
| 57 | 12 Nov | rules (ADR-146 Am 7 p8) | A rule screens only lists its deployer is cleared for | ADR-133/146 | never asked (listed) | in force |
| 58 | 12 Nov | rules | Trends undercount; > 6 citations counted for no one; a firing citing a hidden list withheld whole | ADR-134/146 (inf.) | never asked | in force |
| 59 | 12 Nov | orchestrator | Guides only for places a person may open | ADR-145 Am 10 | told and accepted | in force |
| 60 | 11–12 Nov | orchestrator's D2c brief | Upgrade and volume-expansion runbooks deferred to P9b | PAGE:674 (inf.) | never asked (inf.) | in force |
| 61 | 12 Nov | orchestrator's R1 brief | Client-install acceptance = R1's 28 checks, not spec 08 | ADR-148 Consequences; ADR-142 Am 8 p6 | never asked | v0.5.2 step 6 (audit 5) |
| 62 | 13 Nov | owner | poc at one copy each; no ingest image | PAGE:270-308, 414-419 | owner ruled | in force |
| 63 | 13 Nov | owner | R1 on an Entra stand-in; the real tenant later | PAGE:703 | owner ruled | in force |

Limits of the pass:
- Some lane reports were read only by their "Decisions taken" parts.
- Most briefs were searched for deferral words rather than read in full.
- The build plan's friction rows were scanned by title.
