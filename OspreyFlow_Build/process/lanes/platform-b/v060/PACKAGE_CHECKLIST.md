# v0.6.0 · the package step (stage 3), as a checklist

Prepared offline on 15 November 2026 by platform-b (the orchestrator's assignment: make the one candidate a
mechanical step). Nothing here was published or tagged. **OWNER** marks a step that needs the owner's word: a push, a
tag, a publication, or a change to a `.github/` file.

## What releases, found preparing this

- **The release is the product repository's workflow**, `OspreyFlow_Core/.github/workflows/release.yml`, published
  as `.github/workflows/release.yml` of the product repository (`aykr/OspreyFlow`) by `publish_user_repo_update.sh`.
  On a `vX.Y.Z` tag it checks the CHANGELOG section, then for each of **seven images** (workspace, api, ingest, ner,
  worker, report-sync, superset) builds an amd64 image and scans it with trivy, builds and pushes both platforms by
  the product commit's sha and signs the index keyless with cosign; then writes `versions.lock` (every image any
  option runs, by digest) and signs it, builds, packs and signs the install page, packages, signs and pushes the
  chart, **verifies all of it as `ospreyflow update` will** (`harness.signatures`), and publishes. v0.5.1's run there
  succeeded (14 Nov 06:19Z).
- **The development repository's root workflow is not the release.** `.github/workflows/release.yml` of
  `aykr/OspreyFlow_Dev` builds another list (api, ingest, workspace, harness, laurium) for `ghcr.io/ospreyflow`, and
  on every tag stops at its first job (`ci-status-gate`: v0.5.1's two runs, 43541285777 and 43565802854, both failed
  there; nothing built). `tools/release_local.py` mirrors that workflow, so its `--dry-run` does not dry-run the
  release. **ADR-114 Amendment 47's tag-against-VERSION refusal (a49cf24) sits in that workflow**, behind the gate
  that always fails, so it has never run and would not stop a release.
  - **The owner's rulings (15 November):** the same check for the product workflow is **approved**, as the diff
    `product_release_version.diff` (beside this file: a step at the head of its `notes` job, shown red with tag
    v0.6.1 against VERSION v0.6.0, exit 1, and green with v0.6.0; it applies with rules' `workflows_upgrade_stamp.diff`
    in either order). The development repository's root `release.yml` is **retired**: `retire_dev_release_yml.diff`
    (beside this file) deletes it, for the owner to apply. **`tools/release_local.py` follows the product
    workflow** (built: it reads the matrix and trivy settings as the dry run did, refuses a real push, and replaces
    the lane's `release_dry_run.py`, `tests/test_release_local_matrix.py`). `tools/ci_status_check.py` served only
    the retired workflow's gate.
- **Laurium: settled, not a defect.** The product release neither builds nor locks Laurium's image, and needs
  not: Laurium is for `cloud-platform` alone, refused in words on every other profile
  (`schemas.deployment.OspreyConfig._extraction_engine_suits_the_profile`, ADR-135 Amendment 6;
  `tests/schemas/test_extraction_engine_setting.py::test_laurium_is_refused_on_every_other_profile_in_words`, shown
  red on 15 November with the refusal planted away: it and the translation case failed, 4 of 18). On
  `cloud-platform`, where it is the default engine, INSTALL step 3's `ospreyflow images push` builds it from the
  checkout (`harness/cloud_platform/profile.yaml`'s `ours:`). `harness.laurium.laurium_image`'s release name is
  reachable only by a configuration the schema refuses. (Case-b's P12 change meant to add Laurium to the release,
  `process/lanes/case-b/P12p2_CI.diff`, and went into the development workflow, now retired.)
- **The upgrade stamp:** the workflows' builds take it through rules' `workflows_upgrade_stamp.diff` (the owner's to
  apply); on GitHub's fresh runners there is no layer cache, so the trap cannot occur there meanwhile. **Found and
  fixed here: `ospreyflow images push`**, the cloud-platform install's step 3 (the client's build, and R1's in the
  package test), passed only the profile's build args: it now passes the day's stamp to each image of ours,
  computed in the command (which imports nothing of the product, ADR-114 decision 3) and held equal to
  `harness.upgrade_stamp` (`test_images_push_passes_the_stamp`, `test_the_command_s_stamp_is_harness_s`).

## The dry run (stage 3 preparation; on today's main, nothing leaves the machine)

`python -m tools.release_local --dry-run --tag v0.6.0` (the owner's ruling: it follows the product workflow) reads
the workflow's own matrix and trivy settings (it cannot drift from them; `tests/test_release_local_matrix.py`) and
runs, short of every push, signature and publication (printed as `[would] …`):

| Part | Where | Result on 15 Nov (main as it stood, 0203906) |
| --- | --- | --- |
| `scripts.changelog_check --tag v0.6.0` | the Mac | **PASS**: "v0.6.0 has its section" (101 lines of notes); a tag with none (v0.6.1) refused in words |
| `VERSION` | the Mac | **v0.6.0** |
| the install page: `npm run build -w apps/harness`, packed | the Mac | **PASS**: built, stamped `bb477b60975e`, packed (90 KB) |
| `harness.release_lock` (registries read over the network) | the Mac | **PASS as expected**: refuses naming exactly our five locked images, never pushed (workspace, api, ingest, ner, superset); every third-party image pinned |
| the seven images: `docker buildx build --pull --platform linux/amd64 --load` with the upgrade stamp, then trivy (the workflow's flags) | **the test server** (amd64), main `bd253df`, a `git archive` copy, 16:22–16:25Z | **PASS**: all seven built (workspace 108 MB, api 1.95 GB, ingest, worker and report-sync 942 MB each, ner 2.33 GB, superset 1.45 GB), each with `OSPREY_UPGRADE_STAMP=2026-11-15`; trivy `--scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1` passed on every one, no image with a fixed HIGH or CRITICAL finding. **Warm, not cold**: every stamp layer came from the server's cache (an earlier build the same day with the same stamp; `--pull` still checked each base), so 3 minutes says nothing of a cold build's time; GitHub's runners build cold. The scan tags were removed afterwards |
| `helm package deploy/helm/ospreyflow --version 0.6.0 --app-version v0.6.0` | the test server (R1's pinned helm v3.16.3) | **PASS**: `ospreyflow-0.6.0.tgz` (12 KB); in the same run the notes, the lock (refusing only our five) and the install page passed again; rc 0, every push, signature and publication printed `[would]`. Record: `~/osprey-runs/platform-b.dry/` (`dry.log`, 2,200 lines) |
| cosign signing and `harness.signatures`' verify | — | cannot run offline: keyless signing is the workflow's own GitHub identity |

    # on the test server, in a copy of the candidate, from OspreyFlow_Core:
    PYTHONPATH=.:packages:../OspreyFlow_Build .venv/bin/python -m tools.release_local --dry-run --tag v0.6.0 \
        --out ~/osprey-runs/platform-b.dry

## The package step, in order

Run on the candidate `C`: the development commit the package test (stage 4) passed on, with main's CI green on it.

| # | Step | Command | Who |
| --- | --- | --- | --- |
| 1 | `VERSION` is the tag | `cat OspreyFlow_Core/VERSION` → `v0.6.0` (on main already) | orchestrator |
| 2 | The CHANGELOG's date is the tag's | in `C` itself: `## v0.6.0 — <the tag's date>` (main has 2026-11-18; set it to the day the tag is made), then `python3 -m scripts.changelog_check --tag v0.6.0` | orchestrator (a commit; `C` is then that commit, CI green on it) |
| 3 | The guides say v0.6.0 | `grep 'For OspreyFlow v' OspreyFlow_Core/docs/*.md` (all four say v0.6.0 on main); `make docs-pdf` | orchestrator |
| 4 | The dry run green on `C` (green on main `bd253df`, 15 Nov; run again on `C` if `C` changes an image, the chart or the lock) | `python -m tools.release_local --dry-run --tag v0.6.0` on the test server (above): seven images built and scanned, the chart packaged, the lock refusing only our images | platform-b (queue and lease) |
| 5 | **The product repository gets `C`** | `publish_user_repo_update.sh` (the owner's script, not committed): exports `git archive C OspreyFlow_Core`, stops on a real name, a local path or a private file, commits "OspreyFlow — from <C>" in the product checkout; then `git -C OspreyFlow_user_repo push origin main` | **OWNER** (a push to the public product repository) |
| 6 | The published tree is the tested tree | `git -C OspreyFlow_user_repo diff --stat HEAD~1` against what was expected; `git archive C OspreyFlow_Core` and the product's HEAD tree compared file for file (the one tie between the package test and the release: the commit, not a digest) | orchestrator |
| 7 | **The tag, in the product repository** | `git -C OspreyFlow_user_repo tag -a v0.6.0 -m "OspreyFlow v0.6.0" && git -C OspreyFlow_user_repo push origin v0.6.0`. **Never move or delete a pushed tag**: a failed run ships the next patch number | **OWNER** |
| 8 | The release workflow runs | `gh run watch -R aykr/OspreyFlow` (the run the tag started): notes, seven images, lock, page, chart, the verify step, publish | orchestrator watches |
| 9 | **The development repository's tag** (a marker only, once its root workflow is retired) | `git tag -a v0.6.0 C && git push origin v0.6.0`: with `retire_dev_release_yml.diff` applied, no workflow runs on it | **OWNER** |
| 10 | After publication, as a client sees it | every image in the release's `versions.lock` pulled with an empty `DOCKER_CONFIG` (anonymously); `python -m harness.signatures --lock versions.lock --lock-signature versions.lock.sigstore.json --repository aykr/OspreyFlow --tag v0.6.0` against the published assets; `ospreyflow update --check` on a deployment names v0.6.0 | orchestrator or platform-b |

## Should the package test use this local build's images? (question 3)

**No: the package test builds its own, as the client does, and that is the right test.**

- The client's route for v0.6.0 is the cloud-platform shape, whose INSTALL step 3 **builds our images from the
  checkout and copies the third-party ones by digest into the client's own registry** (`ospreyflow images push
  --registry … --from "$FOLDER"`, `harness/cloud_platform/runbooks.py`). It never pulls the release's signed images.
  R1's INSTALL does exactly that into R1's registry, so the package test (#11) proves the client's own path.
- **Their digests cannot equal the release's, and need not.** The release builds a two-platform index on GitHub's
  runner from the product commit; R1 builds amd64 on the test server from the development commit, on another day,
  with another upgrade stamp. Neither build is reproducible bit for bit (each takes the distribution's updates of its
  day, by design). **The tie is the commit**: the package test passes on development commit `C`, the product commit
  is "OspreyFlow — from `C`", and step 6 checks the published tree is `C`'s `OspreyFlow_Core`.
- **What the release's own images and digests are for**: Lite and Small in pull mode, `ospreyflow update`, and the
  Enterprise chart. They are proven by the release workflow's verify step (step 8) and the anonymous pull and
  signature check (step 10), not by the package test.
- **Using the dry run's images in R1 would add nothing and cost a choice**: they would be pushed into R1's registry
  under another name, and INSTALL step 3 would build its own anyway (it is the step under test). Keeping R1's
  registry across the remake (#11) already makes the second install warm.
