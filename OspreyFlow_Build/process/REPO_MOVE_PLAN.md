# Moving the product repository to Solirius/ospreyflow

> **Withdrawn, 3 November 2026 (ADR-114 Amendment 31).** The Solirius organisation does not let its members
> make packages public or change a repository's visibility, so the move was reversed: the product stays at
> `aykr/OspreyFlow` (v0.4.3), and `Solirius/ospreyflow` and its packages are deleted. The plan below is
> kept as history.

**Status:** planned 1 November 2026, at the owner's request. Runs last, after (owner, 1 November 2026):
1. the GOV.UK deck work in flight;
2. alerting and monitoring as a core feature (`ALERTING_MONITORING_PLAN.md`);
3. the website pages updated to say that OspreyFlow has a fully featured, GDS-compliant UK public
   sector option for all UK departments.

**The owner's request (1 November 2026):** "make repository switch for published to
https://github.com/Solirius/ospreyflow, this will also need to involve moving all the published pages as
well … build in the step to delete the current product repo https://github.com/aykr/OspreyFlow."

**In scope:** the product (user) repository only, `aykr/OspreyFlow`, with its releases, its container
images and chart, and its GitHub Pages site. The developer repository (`aykr/OspreyFlow_Dev`, this
repository's `origin`) stays where it is.

## What exists today (checked 1 November 2026)

| Thing | Where | Notes |
| --- | --- | --- |
| Product source, `main` | `aykr/OspreyFlow`, public | Written by `make publish-user-repo` into `../OspreyFlow_user_repo`, pushed by the owner (`publish_user_repo_first.sh` / `publish_user_repo_update.sh`, untracked, both name `aykr/OspreyFlow`) |
| Tags and releases | `v0.1.0` to `v0.4.1` (six tags; v0.4.1 latest) | Each release carries `ospreyflow-<v>.tgz`, `install-page.tar.gz`, `versions.lock`, each with a `.sigstore.json` |
| Signatures | Sigstore keyless, by `aykr/OspreyFlow`'s `release.yml` | `harness/signatures.py` `Keyless`: an install accepts only a release signed by **its own origin's** release workflow |
| Container images, chart | `ghcr.io/aykr/{api,ingest,workspace,worker,report-sync,superset,ner}`, `ghcr.io/aykr/charts/ospreyflow` | The product's `release.yml` publishes under `ghcr.io/<repository owner>`, so under Solirius they become `ghcr.io/solirius/...` |
| Pages site | `gh-pages` branch → `https://aykr.github.io/OspreyFlow/` | `index.html`, `intro-video.html`, `.nojekyll` (ADR-114 Amendment 28; `marketing_site/publish_pages.sh`) |
| Target | `Solirius/ospreyflow`, public, **empty** (created 1 Nov 2026 07:35) | No Pages yet |
| Places that name the old address | `harness/render.py` `RELEASES_URL`; `marketing_site/deploy/README.md` and its exported `index.html` (`repoUrl`); the two publish scripts; `OspreyFlow_presentations/.../PID_DEMO_SETUP_GUIDE.md` (clone command); ADR-114 Amendments 21, 27, 28 (history, left as written) | |

## Stage 1 — the owner's rulings (answered 1 November 2026)

1. **"Solirius" is no longer refused.** "Remove the clause that prevents the use of the word Solirius.
   I want to embrace the theme that 'OspreyFlow is an open source intelligence mapping,
   anti-money-laundering and fraud detection platform, developed by Solirius Reply and released under
   the Apache License 2.0.'" `solirius` comes out of `AUTHORSHIP_PATTERN` (ADR-034 §B5, by amendment).
   The personal identifiers (`ayan.?kar`, `ayankarsolirius`) stay refused. ADR-114 Amendment 28's
   reason for the separate `gh-pages` branch (the site names the company) no longer applies, but the
   branch stays as the way the site is published.
   - Tests: the gate passes "Solirius Reply" and still refuses each personal identifier, each shown red
     first.
   - The statement goes where the product describes itself: the README's opening, the install page,
     the marketing site, and the welcome page's About section.
   - `NOTICE` keeps "Copyright 2026 The OspreyFlow Authors", and the GOV.UK footer keeps "Built with
     OspreyFlow, open source." (the owner, 1 November 2026). The full statement goes in About, not in
     GOV.UK chrome.
2. **The method:** push to `Solirius/ospreyflow`, release there, then delete `aykr/OspreyFlow`.
3. **The old releases are not copied.** The first release in the new repository is v0.4.2. The owner
   will ask every existing user to wipe their install and clone again from the new repository, so no
   in-place move of old installs is planned.
4. **The old images and chart under `ghcr.io/aykr/` are deleted with the repository** (Stage 5).
5. **The site's address is `https://solirius.github.io/ospreyflow/`**, with no custom domain.

## Stage 2 — changes in the developer repository (one branch, tests first)

1. The packaging-gate amendment from ruling 1, with its red-then-green tests, and the statement in
   the README, the install page, the marketing site and About.
2. `harness/render.py` `RELEASES_URL` → `https://github.com/Solirius/ospreyflow/releases`.
3. `marketing_site/deploy/README.md` and the site's `repoUrl` → the new repository; export the site again.
4. An ADR-114 amendment recording the move (the product repository, the images' registry, the site's
   address, the old repository deleted) and a line in `process/FDE_HANDOVER.md`'s remotes.
5. Outside git: the two publish scripts' remote, and the demo setup guide's clone command.
6. `make ci` green.

## Stage 3 — publish to the new repository

1. Check the organisation's settings first: Actions allowed for the repository, `GITHUB_TOKEN` allowed to
   write packages, public Pages allowed, and the owner holding admin on the repository.
2. `make publish-user-repo` into `../OspreyFlow_user_repo`; point its `origin` at
   `https://github.com/Solirius/ospreyflow.git`; push `main` with its history. **Do not push the old tags**:
   each tag push runs `release.yml`.
3. Wait for `ci.yml` to go green on `main` (`release.yml` refuses a commit without a green CI run).
4. Tag and push `v0.4.2`. `release.yml` builds, scans and pushes the images and chart to
   `ghcr.io/solirius/`, and publishes the release with its signatures. Make the packages public.
5. The site: push the `gh-pages` branch (from `marketing_site/publish_pages.sh`, now aimed at the new
   repository) and turn on Pages from `gh-pages`, at `https://solirius.github.io/ospreyflow/`.

## Stage 4 — check the new home before deleting anything

- A fresh install from `Solirius/ospreyflow` (`OSPREYFLOW_REPO=https://github.com/Solirius/ospreyflow.git sh install.sh`)
  installs v0.4.2, pulls `ghcr.io/solirius/` images, and verifies the release signature.
- `ospreyflow update` on that install finds the release and accepts its signature. A release signed by
  any other workflow is still refused (the existing `signatures` tests, plus one live check).
- The site answers at its new address, with the video and the GitHub link pointing to the new repository.
- Nothing in the new repository or its release carries a personal identifier.

## Stage 5 — delete `aykr/OspreyFlow` (the owner's go-ahead on the day, not this plan's)

1. Say exactly what the delete removes: the repository and its history, six releases and their assets,
   the Pages site at `aykr.github.io/OspreyFlow` (with no redirect), and any issues or stars. Then wait
   for the owner's go-ahead.
2. Keep a copy first: `git clone --mirror https://github.com/aykr/OspreyFlow.git`, and every release's
   assets downloaded, into `OspreyFlow_Data/archive/aykr-OspreyFlow-<date>/` (outside git).
3. `gh auth refresh -s delete_repo`, then `gh repo delete aykr/OspreyFlow --yes`.
4. Delete the `ghcr.io/aykr/` images and chart (ruling 4): `api`, `ingest`, `workspace`, `worker`,
   `report-sync`, `superset`, `ner` and `charts/ospreyflow`. Leave `noggin`, which belongs to no repository.
5. Check: the old address gives 404, and the new site, release and install still work.

## Who is affected

An install made from `aykr/OspreyFlow` stops finding updates once that repository is deleted, and can no
longer pull its images once they are deleted. The owner will ask each user to wipe their install and
clone again from `Solirius/ospreyflow` (ruling 3), so send that message before Stage 5. The owner's two local
deployments run from the developer repository and are not affected.
