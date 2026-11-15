# v0.6.0 · the release steps (package checklist steps 5 to 9), the orchestrator's

Written by platform-b. **Run by the orchestrator under the owner's word in advance**
(`process/lanes/v060/OWNER_WORD_IN_ADVANCE_2026-11-15.md` §1, stage 5), only once the package test (stage 4) has
passed on `C` with every check, none waived, skipped or re-run to green without its reason written down. No lane runs
these. `C` is the candidate, main's **`09f1fbe`** (09f1fbe8c28f5557b5431f219c81116bcd5e39ef) itself: checklist steps
1 to 3 needed no change under `OspreyFlow_Core`, so no candidate commit was made (the orchestrator's trigger, 15
November). CI run **43756479074** is green on it (attempt 1, 41 of 41 jobs); the package test's record is
**`<record>`** (filled in when stage 4 ends).
`ROOT=/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform`.

**Stop** (the word's §2), leave everything as it is, write it at the top of `MORNING.md`, on: a step's check failing
for anything but a recorded reason outside the product (re-run it then, and write the reason); any part about to make
something public that is not already (the one point is marked **PUBLIC?** below); the release made from anything but
`C`.

## Before step 5: publishing from `C`, not from main's head

`publish_user_repo_update.sh` publishes **its checkout's `HEAD`** (`make publish-user-repo COMMIT=HEAD`) and names that
`HEAD` in the product commit's message. Both safeguards hold (the orchestrator's ruling, 15 November): nothing merges
to main between `C` and the publish apart from records under `process/` (never published, but they move `HEAD`),
**and** the publish runs from `C` itself, checked in step 6. So, first:

    git -C "$ROOT/ospreyflow" status --porcelain                  # empty
    git -C "$ROOT/ospreyflow" checkout --detach 09f1fbe8c28f5557b5431f219c81116bcd5e39ef
    git -C "$ROOT/ospreyflow" rev-parse HEAD                      # 09f1fbe8c28f5557b5431f219c81116bcd5e39ef
    git -C "$ROOT/OspreyFlow_user_repo" status --porcelain         # empty
    git -C "$ROOT/OspreyFlow_user_repo" fetch origin && git -C "$ROOT/OspreyFlow_user_repo" status -sb   # not behind origin/main

## The steps

| # | Step | Command | Expected |
| --- | --- | --- | --- |
| 5 | The product checkout gets `C` | `sh "$ROOT/ospreyflow/OspreyFlow_Build/scripts/publish_user_repo_update.sh"` | it stops on a real name, a local path or a private file (any stop is a §2 stop); otherwise prints the diff's stat, commits `OspreyFlow — from 09f1fbe` in `OspreyFlow_user_repo` (local only) and prints the push command |
| 6 | The commit is `C`'s tree, before anything leaves the machine | `git -C "$ROOT/OspreyFlow_user_repo" log --oneline -1` names `09f1fbe`; `OUT=$(mktemp -d)/x; make -C "$ROOT/ospreyflow/OspreyFlow_Build" publish-user-repo COMMIT=09f1fbe8c28f5557b5431f219c81116bcd5e39ef OUT="$OUT"; diff -r --exclude .git "$OUT" "$ROOT/OspreyFlow_user_repo"` | no difference: the tie between the package test and the release is the commit. A difference stops the run (`git -C "$ROOT/OspreyFlow_user_repo" reset --hard origin/main` undoes the local commit, nothing pushed) |
| 6b | **The push** (**PUBLIC?**: see below) | `git -C "$ROOT/OspreyFlow_user_repo" push origin main` | `aykr/OspreyFlow` main is the new commit |
| 7 | The tag, in the product repository | `git -C "$ROOT/OspreyFlow_user_repo" tag -a v0.6.0 -m "OspreyFlow v0.6.0"` then `git -C "$ROOT/OspreyFlow_user_repo" push origin v0.6.0` | the release workflow starts. **Never move or delete a pushed tag**: a failed run ships v0.6.1 (a §2 stop) |
| 8 | The release workflow runs | `gh run watch -R aykr/OspreyFlow --exit-status $(gh run list -R aykr/OspreyFlow -w release.yml -L 1 --json databaseId -q '.[0].databaseId')` | the tag is VERSION (`The tag is the code's own VERSION`); notes; seven images built with the stamp, scanned, pushed by `C`'s product sha for two platforms and signed; the lock signed; the install page; the chart pushed and signed; the verify step (`harness.signatures`, as `ospreyflow update` will); `gh release create` |
| 9 | The development repository's marker tag | `git -C "$ROOT/ospreyflow" tag -a v0.6.0 09f1fbe8c28f5557b5431f219c81116bcd5e39ef -m "OspreyFlow v0.6.0"` then `git -C "$ROOT/ospreyflow" push origin v0.6.0` | no workflow runs on it (the root `release.yml` is retired, `retire_dev_release_yml.diff` on main) |
| after | Back to main | `git -C "$ROOT/ospreyflow" checkout main` | — |
| 10 | As a client sees it | every image in the release's `versions.lock` pulled with an empty `DOCKER_CONFIG`; `python -m harness.signatures --lock versions.lock --lock-signature versions.lock.sigstore.json --repository aykr/OspreyFlow --tag v0.6.0` against the published assets; `ospreyflow update --check` on a deployment naming v0.6.0 | all pulled anonymously, verified, v0.6.0 named |

## PUBLIC?: the one point that could make something newly public

**Steps 6b to 8 publish, and should make nothing newly public.** Checked on 15 November (~18:30Z), anonymously:

- `aykr/OspreyFlow` is a public repository; the push adds a commit and the tag to it, and the workflow a release
  page on it.
- The workflow pushes to **exactly the packages v0.5.1 did**: its matrix on main is v0.5.1's, line for line
  (workspace, api, ingest, ner, worker, report-sync, superset), and the chart to `ghcr.io/aykr/charts/ospreyflow`.
  An anonymous registry token lists the tags of all eight (HTTP 200), so each is public already; v0.6.0 adds tags
  and signatures to them.

What would make it newly public, and stops the run before step 6b: the matrix or the chart's destination on `C`
naming a package not in that list (a new package's visibility is GitHub's default, not ours), or step 6's tree
holding a file the publish script's checks should have refused. Check just before 6b:

    git -C "$ROOT/OspreyFlow_user_repo" show HEAD:.github/workflows/release.yml | grep -E 'service: |oci://'
    # the seven services above and oci://ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/charts, nothing else

## The owner's diffs: all three on main already (checked 15 November)

`product_release_version.diff` (the product workflow's tag-against-VERSION step), rules'
`workflows_upgrade_stamp.diff` (the stamp in both of its builds) and `retire_dev_release_yml.diff` (the development
repository's root `release.yml` gone) are each applied on main, so `C` carries them and step 9 starts no workflow.

## Back to the owner (the word's §5)

One line at "release made": the product commit (`OspreyFlow — from 09f1fbe`), the tag, the workflow run, the seven
image digests and the chart's, the release's URL; and whether step 10 passed.
