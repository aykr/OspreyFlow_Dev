# The sites against release v0.5.1

The docs lane, 14 November 2026, at the orchestrator's word. `build.py` refused to build once the CHANGELOG named v0.5.1
while the pages had been checked against v0.5.0 (`CHECKED_AGAINST`). Every claim the pages mark as in the release, or as
only on main, was checked again. The checks were against the v0.5.1 tag (e024f7d), v0.5.0 (4b8de6c, CHANGELOG
2026-11-10) and main at 186144b, and `CHECKED_AGAINST` is now `v0.5.1`. Paths are relative to `OspreyFlow_Core/`. The
claims in the two animations were checked on 13 November (`sites2-facts.md`). Their search and navigation wording stays
as it is until step 5's sweep, as the orchestrator ruled.

**Next check:** the pages are checked again against v0.5.2 at the cut, before the owner says "publish". `build.py`
refuses to build until that check is done and `CHECKED_AGAINST` is `v0.5.2`.

## Moved from "On main, coming with the next release" into the release

Each item below was on main and not in v0.5.0: its file is absent at 4b8de6c and present in the v0.5.1 tag.

| Claim | Where it now stands | Source in v0.5.1 |
| --- | --- | --- |
| A profile for shared government Kubernetes platforms: one namespace, the platform's managed services, non-root containers, a single-copy shape for a proof of concept, sign-in through Entra ID | Features, *Admin and access*, a card of its own: "Installed and checked on a test cluster, not yet on a platform. In this release, loads there are started by hand and reporting is not on it; the administration guide's section 6a has every limit." | `harness/cloud_platform/profile.yaml`; CHANGELOG v0.5.1: "The `cloud-platform` profile's proof-of-concept shape (`shape: poc`) was installed on a kind cluster…", "People sign in with Entra ID on that profile", and its *Known limits*: "**loads are started by hand** in the Ingest Studio…", "Reporting (Superset) is not on this profile. The administration guide's §6a has the whole of it." |
| S3 and Athena as sources | Features, *Ingest Studio*, "2 Sources": "and on the shared-platform profile S3 buckets and Athena" | `services/ingest/connectors/s3_connector.py`, `athena_connector.py`; administration guide (v0.5.1) Appendix A `cloud_platform.connector_sources`, "the S3 buckets and Athena workgroups a cloud-platform deployment declares"; CHANGELOG v0.5.1 *Known limits*: "One S3 read takes at most 1,000 objects; … Athena reads its default catalog alone" |
| A second, open-source extraction engine for structured facts in documents, on the shared-platform profile (the owner's item 3, "on the shared-platform profile") | Features, *Models and questions*, "Extraction": "On the shared-platform profile, a second, open-source extraction engine for structured facts in documents is installed and runs; no screen uses it yet." | `packages/adapters/extract_laurium/`; administration guide (v0.5.1) Appendix A `models.extraction_engine`: "Laurium on the `cloud-platform` profile alone"; §6a.1: "**no screen reaches it yet** … Laurium is rendered and runs while no analyst action reaches it, until a screen calls the review queue's extraction (*coming*)", so it is not in "coming next" either (the lane review) |
| Routing to your organisation's own AI gateway, or to Amazon Bedrock in London, on the shared-platform profile | Features, *Models and questions*, "Hosted engines, by permission": "On the shared-platform profile, your organisation's own AI gateway, or Amazon Bedrock in London, checked so far against a stand-in gateway, not yet against AWS or an organisation's own." | `harness/cloud_platform/profile.yaml`, "ADR-135 Amendment 4: Bedrock in London only"; administration guide (v0.5.1) §6a.9, "an engine as your organisation's own AI gateway (by a token) or Amazon Bedrock in London", and its **Not yet tried**: "The route is checked as rendered, against a stand-in gateway, and not against AWS or your organisation's gateway" |
| ospreyflow.net, *Services*, "A shared government platform": "arriving with the next release" | "A profile for shared Kubernetes platforms, in the current release: installed and checked on a test cluster, not yet on a platform." | As the profile's row above |

## "On main, coming with the next release", refilled

Only what v0.5.1's CHANGELOG says the next release brings, "**v0.5.2** brings scheduled runs, reporting and the
data-safety fixes" (its *Known limits*), each held by main at 186144b. No date is given.

| Claim | Source on main (186144b) |
| --- | --- |
| On the shared-platform profile, scheduled runs: a pipeline's schedule and watched folder, rules, watches and list refreshes running as their owner, while the owner has signed in within the last 24 hours | `packages/principal_auth/__init__.py`: an owner resolved from *Admin › People* on Entra ID, refused when they "[have] not signed in to OspreyFlow within the last 24 hours" (ADR-148 Amendment 16); the runs are those the v0.5.1 CHANGELOG's *Known limits* lists as refused |
| Reporting on the shared-platform profile, through Apache Superset | `harness/cloud_platform/profile.yaml`: `{site: dashboards, workload: superset, port: 8088}` and the `superset` image (ADR-148 Amendments 9 to 11) |
| The shared-platform profile's data-safety fixes, to its backups and restore | `harness/cloud_platform_backups.py`: the backup set's shared parts, `shared_parts()` and `INGEST_PART` (ADR-148 Amendment 13) |

## Left as it is: *Questions*

v0.5.1 renamed the rail's *Questions* to *Ask & Chat* (CHANGELOG v0.5.1, *The workspace*). The pages keep "Questions"
on Home, on Features and in the screenshot's caption: that is navigation wording, kept until step 5's sweep, when the
screenshots are taken again too (the lane review).

## Checked and unchanged

- **Get started.** The three commands are unchanged: `install.sh` and `install.ps1` are in the tag (`install.sh` runs
  `uv tool install --editable "$product/cli"`, as the CHANGELOG's "Before you update" says), and so are `ospreyflow
  doctor`, `install --mode lite` with `--gui` and `--config install.yaml --yes`, and `open`. Lite still needs "at
  least 16 GB available to Docker (32 GB is comfortable)" and "at least 60 GB free" (administration guide, v0.5.1,
  §2). `ospreyflow update --check` is unchanged too.
- **UK public sector** (ospreyflow.org) and **Features**' other sections: nothing these pages say is in the release was
  removed or changed in v0.5.1. v0.5.1's GOV.UK change is the slim header and one-line banner inside a case (CHANGELOG
  v0.5.1, *The workspace*). The banner is still a GOV.UK notification banner (`apps/workspace/src/shell/ContextBanner.tsx`
  draws `govuk-notification-banner` in the tag), and the four places are unchanged (user guide, v0.5.1, §1).
- **The release badge** on every page reads v0.5.1, from the CHANGELOG at build time. Pages whose words did not change
  differ from their v0.5.0 build in the badge alone.

## The owner's item 4: Contribute

"A maintainer runs the project's checks on it before it is merged: tests, licence checks, accessibility scans and image
scans" is struck from *How to contribute*. The step now reads "Open a pull request." The owner's word, 14 November: it
returns when the public repository runs checks on a pull request.
