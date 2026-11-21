# PL13, the scout: can OspreyFlow build its own gateway image from the MIT code alone? (scout, 21 November 2026)

Findings only. The scout changes no product file, image, model address or demo. Everything below was **read** or **run** in
scratch (the pinned image's own filesystem exported to a folder of its own; one throwaway network per run with a Postgres, a
stand-in provider and a gateway on an ephemeral 127.0.0.1 port, no mount from the repository or the home folder; a Python
virtual environment of its own; PyPI's own files). Where a thing was not read or not run, the cell says "not read" or "not
run" and why. The image is `ghcr.io/berriai/litellm` at the digest `harness/render.py` pins,
`sha256:d295634e09c648dcdb72c4cc2dd226f5fb87823a73e88cbbed6f205e4deb044b`: litellm 1.101.0, built from the publisher's source at
revision 18243cd7, arm64 layer read (the local copy).

## The nine answers

| # | Question | Answer | Evidence (what was read or run) |
| --- | --- | --- | --- |
| 1 | Does the gateway start and serve with `/app/enterprise` absent? Which of the product's gateway tests pass and fail without it? | **Yes, and also with the installed `litellm-enterprise` package absent.** Three scratch gateways on the same config the renderer writes: (a) the pinned image untouched, (b) `/app/enterprise` removed, (c) `/app/enterprise` and the installed package removed. Each came up (liveliness in about 22 seconds) and answered the same 24 calls with the same 24 status codes: liveliness and readiness, `/v2/model/info`, `/credentials` create and delete, `/model/new` and `/model/delete` (a credential, an address, a price), `/key/generate`, `/key/update`, `/key/list`, `/key/delete`, chat and embeddings under an engine key with a tag, the 403 for a model outside the key, the renderer's own local chat, embeddings and transcription routes, and `/tag/daily/activity` (which showed the call's tag in all three). The repository's real-gateway test `test_the_key_round_trip_against_the_real_gateway` PASSED against (a) and against (c). Tests: every key-handling test the brief names runs only against the in-process stand-in, never a gateway or Docker, so the folder cannot affect it: main has 300 passing (the address-change test, the stand-in gateway tests, the admin routes, engine keys, kinds and engines) and AD1a's tip 3dd9ec2 has 260 passed and 1 xfailed (the key-paths, key-commands, engine-checks, key-review and address-change tests with the stand-in tests). **Run against the real image at all:** only the live tests (`test_model_gateway_live.py`, `test_laurium_key_live.py`, `test_laurium_reads_a_real_model_live.py`; each skips unless pointed at a gateway) and GitHub CI's `conformance-model` and `conformance-model-vision` jobs (two `docker run` lines naming the pin). **Not run:** the CI jobs (they pull Ollama models and Whisper weights from the internet), the Laurium live tests (they need Laurium and a real model), the real-`pg_dump` test (it skipped: this Mac's guard forbids Docker use from a test), Bedrock (no AWS). **Usage live test:** `test_usage_a_request_rate_and_a_token_budget_against_the_real_gateway` PASSED against (a) and against (c) (the real gateway enforces a request rate and a token budget; not run against (b), which differs from (c) only by the package). | Run: `docker create` and `docker export` of the pinned image; `docker build` of two scratch images (`rm -rf /app/enterprise`, and that plus `rm -rf` of the package and its dist-info); a route script (24 calls) against each; the repository's `test_model_gateway_live.py` through pytest against (a) and (c) with a refusing stand-in provider I wrote (right key accepted, wrong key 401, unknown model 404; synthetic keys made at run time); pytest of the named files on main and on a read-only `git archive` of AD1a's tip. Read: `tests/services/api/test_model_gateway_live.py`, the CI file's two Start LiteLLM steps. |
| 2 | Does the open-source code import anything from `/app/enterprise` at start-up or on any route the product uses? Name each import. | **Yes, three imports of the folder, all swallowed when it is absent; and about thirty imports of the installed `litellm_enterprise` package, all guarded except two on routes the product does not use.** The folder: (i) litellm/proxy/proxy_server.py line 782 `from litellm.proxy import enterprise` then line 786 `import enterprise`, at start-up, in `try ... except Exception: pass` (loads a 16-byte `__init__.py`); (ii) litellm/proxy/hooks/__init__.py line 49 `from enterprise.enterprise_hooks import ENTERPRISE_PROXY_HOOKS`, at start-up, in `except ImportError`, which adds two hooks, `managed_files` and `managed_vector_stores` (LiteLLM's own managed-files API: the product uses neither); (iii) litellm/proxy/management_endpoints/customer_endpoints.py line 217 `from enterprise.enterprise_hooks.blocked_user_list`, only on `/customer/block` (answers 400 when absent; not used). The folder's own `enterprise_hooks/__init__.py` imports from the *package*, not from the folder's code. The package, at start-up, each in `try` and `except`: proxy_server.py 793-794 (routes and `EnterpriseProxyConfig`), litellm_core_utils/litellm_logging.py 206-221, proxy/utils.py 46-55, proxy/auth/user_api_key_auth.py 111; on a route, each guarded: proxy/auth/route_checks.py 77 (every management route; `except Exception: pass`), key_management_endpoints.py 1096 (every `/key/generate`), key_management_event_hooks.py 419-537 (email on key events), proxy_server.py 9779 and 9810 (batch polling jobs), public_endpoints.py 355. Config-gated and not in the renderer's config: callback_utils.py 187-296 (seven named callbacks), guardrail_initializers.py 149, custom_guardrail.py 1000 and 1027 (an `ImportError` raised for a default-on guardrail), custom_logger_registry.py 114-123. Unguarded and unused: response_api_endpoints/endpoints.py 371 (Responses API with `background=true`). Measured: with both gone `proxy_server` imports, `enterprise_proxy_config` is None, `premium_user` is False, and the 24 calls in row 1 are unchanged. | Read: every match of `litellm_enterprise`, `from enterprise`, `import enterprise` and `enterprise_hooks` in the installed litellm (47 hits in 18 files), each with its surrounding lines; `docker/Dockerfile` at the image's revision (its own comment: "enterprise/ is imported by source path at runtime"). Run: an in-image probe of what a console script sees (`/app` reaches `sys.path` through litellm's own `prisma_migration.py` line 13, so `import enterprise` succeeds at start-up in the shipped image) and, in variant (c), `find_spec` for both names (both absent, `PackageNotFoundError` for the metadata). |
| 3 | Does building from the MIT source, or installing the package, pull in `litellm-enterprise`? How is it excluded, and does anything break? | **Yes, by default, and it is proprietary.** litellm 1.101.0's `proxy` extra has the hard line `Requires-Dist: litellm-enterprise==0.1.65 ; extra == 'proxy'` (METADATA line 62; PyPI's own JSON for 1.101.0 says the same), and `litellm-enterprise` 0.1.65 declares `License-Expression: LicenseRef-Proprietary` (its METADATA, its pyproject, and PyPI's record). The pinned image carries it twice: as the folder and as the installed package (142 Python files, from `file:///app/enterprise`). **The PyPI sdist (3434 files) and wheel (3260 files) of litellm 1.101.0 contain no `enterprise/` folder at all.** Exclusion that works: a uv override file with the one line `litellm-enterprise ; python_version < "0"`. Resolved with `uv pip compile` (the package is gone from the 340-line result, `litellm-proxy-extras==0.4.94`, which is MIT, stays) and installed for real into a scratch virtual environment (112 packages): `litellm_enterprise` and `enterprise` are not importable, `uv pip check` reports "All installed packages are compatible", `proxy_server` imports, `enterprise_proxy_config` is None, `premium_user` is False. Nothing breaks: see rows 1 and 2. **Do not derive from the publisher's image**: a later `rm` hides the folder but its layers stay in the image and are still shipped; build from PyPI's files in a fresh stage. | Read: `litellm-1.101.0.dist-info/METADATA` in the image, `litellm_enterprise-0.1.65.dist-info/METADATA` and `direct_url.json`, `enterprise/pyproject.toml`, PyPI JSON for litellm 1.101.0, litellm-enterprise 0.1.65 and litellm-proxy-extras 0.4.94. Run: downloaded the sdist and one wheel and checked their SHA-256 against PyPI's (734ab2b8... for the sdist), listed both; `uv pip compile` with and without the override; `uv venv` and `uv pip install` of `litellm[proxy]==1.101.0` with the override; `uv pip check`. The image's litellm package is byte-identical to the PyPI wheel (3254 of 3255 files; the one difference, `rust_bridge/_native.abi3.so`, is a compiled file for another CPU, and I compared an x86-64 wheel with an arm64 layer). |
| 4 | Which gateway features does OspreyFlow use, and is each in the MIT code? | **Every one is in the MIT package; none is behind the publisher's licence key.** Used: the master key; virtual keys, one per hosted engine (`/key/generate`, `/key/update`, `/key/delete`, `/key/list`) with `models`, `rpm_limit`, `tpm_limit`, `max_budget`, `budget_duration` and `metadata`; budgets and rate limits per key; routing from `litellm.yaml` (`ollama_chat`, `ollama` and an OpenAI-compatible route) and entries made at run time (`/model/new`, `/model/delete`, `/v2/model/info`, `store_model_in_db`); named credentials (`/credentials` create, read by name, delete); a per-call tag in the request's `metadata.tags` read back by `/tag/daily/activity`; chat, embeddings and transcription; Postgres through Prisma (`litellm-proxy-extras`, MIT); `/health/liveliness`; the AWS IAM route for Bedrock. Not used: teams, users, the admin UI, SSO, guardrails, callbacks, alerting, email, the Responses API, key `tags`. **The publisher's licence gate (`premium_user`, read from `LITELLM_LICENSE`) is itself MIT code** and guards, among others, key `tags` (line 1181), `model_max_budget` (7082), key regeneration, `/spend/report` and wildcard model access groups: the product uses none of them, sets no `LITELLM_LICENSE`, and every call above worked with `premium_user` False. A tag-based spend read is not gated (it worked unlicensed). | Read: `packages/adapters/model_litellm/client.py`, `usage.py`, `stand_in.py`'s header, `services/api/model_admin.py` (`add_entry`, `put_credential`, `put_engine_key`, `key_limits`, the key listing), the rendered `litellm.yaml` (`render_litellm_config`'s own output, saved and used for every run), `harness/render.py`'s `litellm` service. Searched for `premium_user` and `_premium_user_check` in the key, model, credential, tag and spend endpoint files. Run: the 24 calls and the live round trip. Each route's handler was found in the PyPI wheel. Not run: the Bedrock IAM route (no AWS account), the admin UI, any hosted provider. |
| 5 | The smallest build: base image, pinned version, what the Dockerfile copies, how the pin is recorded in the register and `versions.lock`. | **Proposal for the build, not built.** Base: the publisher's own, `cgr.dev/chainguard/wolfi-base@sha256:e624c5d5e42382ce7165ddafcbbf8e6769a24cbd02ea6114b880b05ae5ba2a8d` (read from its Dockerfile at revision 18243cd7; every measurement in ADR-135 was taken on it), with `apk add bash openssl tzdata nodejs python-3.13 libsndfile` (48 packages, none commercial). Pin: `litellm==1.101.0` and `litellm-proxy-extras==0.4.94` from PyPI, extras as the pinned image (`proxy`, `proxy-runtime`, `extra_proxy`, `semantic-router`, `saml`, `bedrock-realtime`; trimming them is a later, measured choice), the versions of every other package held by a constraints file made from the pinned image's own venv, `litellm-enterprise` removed by the override in row 3. A builder stage installs; the runtime stage copies only: the venv, `docker/` (the two entrypoint scripts), `schema.prisma`, `prisma_migration.py` and `/opt/prisma` (the Prisma CLI and engines, which need the network at build time). **It never copies `/app/enterprise`.** A build-time licence gate (the `ner` image has one: `services/ner/licence_gate.py`) must fail on `litellm-enterprise` or any proprietary licence and be shown red by installing it (rule 15). **Register** (PL11's `spec/LICENCE_REGISTER.yaml` and the register tool `licence_register` (a module of PL11's branch, not on main) are on branch `lane/slice-PL11`, **not merged**, not on main): remove `ghcr.io/berriai/litellm` from `HELD_FOR_OWNER`, and add rows for each new `FROM` (the wolfi base, the uv image) with the licence read at the pin; the gate reads every Dockerfile under the product folder and fails on a base with no row. **`versions.lock`**: no change to `harness/release_lock.py`: once `harness/render.py` names the gateway as an owned image it appears in the lock as `repository@digest` with its tag the commit and its source the registry, as the other owned images do. **Two things found by reading that the build must handle:** `ServiceImage.owned` also gives a service `env_file: deployment.env` (render.py line 1039), which would hand the gateway the whole deployment's secrets, so the gateway needs "built by us, no env file" with a test; and the pin sits in four more places: `deploy/compose/dev.yaml` line 290 (the test `test_the_rendered_model_proxy_is_the_developer_stacks` holds the two equal), `.github/workflows/ci.yml` lines 980 and 1032 (protected: a diff), the cloud-platform manifest and the administration guide. | Read: `harness/render.py` (lines 631-684, 914-948, 1039, 1536-1590, 1798-1860), `harness/images.py` (`ServiceImage`), `harness/release_lock.py`, `harness/signatures.py`, `harness/bundle.py`, `harness/update.py`, the publisher's `Dockerfile` at revision 18243cd7 (fetched), `docker history` of the pinned image, PL11's register and the register tool `licence_register` (a module of PL11's branch, not on main) (read with `git show` from its branch). Run: the uv override (row 3). **Not run:** any Docker build of the proposed Dockerfile (the build that follows this scout), a trivy scan of it (the scan belongs to that build, and a fresh resolution may find fixable HIGH or CRITICAL findings the pinned image does not carry). |
| 6 | Protected files a release of the new image would touch, as diffs that pass `git apply --check`. | **Five files, in two patches with different timing.** **Patch 1, safe to apply at any time** (before or after the build, and before or after the render switch): `harness/signatures.py`, `harness/bundle.py` and `harness/update.py`, below. **Patch 2, apply only once the build's `deploy/litellm/Dockerfile` is on main** (the build is a later round; the path is a proposal and no such file exists today): `release.yml` and the Core Makefile. Applied before that file exists, patch 2 turns `make ci` red for every merge (Core's `check` would run `docker build -f deploy/litellm/Dockerfile`, and Build's `ci` runs Core's `check` first) and fails the next tagged release's matrix job the same way. `OspreyFlow_Core/.github/workflows/release.yml` (patch 2): one new matrix entry after the superset line (about line 65); the scan (trivy at lines 87-94), the push, the keyless signing and the lock verification are all driven by the matrix, so they need no other change. `OspreyFlow_Core/Makefile` (patch 2): `trivy-image-litellm` added to the `.PHONY` line (1), to `check` (13), and as a target after `trivy-image-laurium` (92-94). **The signature check needs more than one line, because every lock to date names the publisher's gateway under the service name `litellm`** (`_render_versions_lock`, `harness/render.py` 1844-1855 writes `service: litellm`, `repository: ghcr.io/berriai/litellm`, a real digest). Adding `litellm` to `OPTIONAL_OWNED_SERVICES` alone (this file's first draft) would hand that image to `cosign verify` against OspreyFlow's release workflow, which it can never pass, so every older lock, every older bundle and main's own next release would be refused. Measured in memory with a fake cosign that refuses what is not ours: the one-line change refuses the older lock (5 images checked, the publisher's among them); main as it is, and the patch below, verify it (4 checked). **Patch 1:** `harness/signatures.py` adds `litellm` to `OPTIONAL_OWNED_SERVICES`, a `THIRD_PARTY_REPOSITORIES = ("ghcr.io/berriai/",)` and one predicate `is_signed_image(service, repository)` (a signed service **and** a repository not under a third party's) that `owned_references` now uses. `harness/bundle.py` line 320 (`entry.get("service") in SIGNED_SERVICES`, the offline check of a bundle) and `harness/update.py` lines 368-369 (`repository.endswith(f"/{s}")`, the check of what is running) each had their own name-only copy of the test and use the new rule too. **Patch 1 is safe in any order against the render switch:** before the build names our gateway no lock entry changes meaning; after it, `ghcr.io/<owner>/litellm` is checked and, unsigned, is refused (shown in memory). **The build that follows commits these tests with it, each shown red against the one-line change:** an older lock naming `ghcr.io/berriai/litellm` under `litellm` is not in `owned_references` and `verify_release` passes it with a cosign that refuses it; `make_bundle`'s offline check and `verify_running` skip it; a lock naming `ghcr.io/<owner>/litellm` unsigned is refused by name. Also protected: `.github/workflows/ci.yml` lines 980 and 1032 (the conformance jobs run the publisher's image; they move to ours once it exists): **no diff yet, it is written in the build, and it waits for our image to be on the registry**, so it has patch 2's timing, never earlier. The two patches are in the last section and each passes `git apply --check` against main on its own; the Dockerfile path patch 2 names, `deploy/litellm/Dockerfile`, is a proposal. **They touch the same lines PL7d's diffs will** (the matrix anchor, the `OPTIONAL_OWNED_SERVICES` line, the target block): the owner applies one and the other is rewritten against the new main. | Read: `release.yml` in full (187 lines), `signatures.py` in full, `bundle.py` 300-335, `update.py` 320-385, `images.py`, `release_lock.py`, `render.py` 1835-1865, the Makefile lines 1, 13 and 91-95, `tests/harness/test_signatures.py` (its `_lock` helper and the Superset case, which the new cases copy). Run: a script (a heredoc; no file written) took each file's text from `git show HEAD:<path>`, made the edits, built the diff with `difflib` and ran `git apply --check` on it (passed; base c71c727, and the five files' blobs are identical on main aad2df3); ran `ruff check` and `ruff format --check` on each patched file from stdin (check clean; `bundle.py` was not format-clean before and is no worse); in round 3 split the patch by file into the two patches below and ran `git apply --check` on each alone and on both together (all pass, against this branch's tip and against main aad2df3, whose five files are the same blobs); and loaded the unpatched, the one-line and the patched `signatures.py` in memory to run `verify_release` on an older and on a new lock. **Not run:** the existing `test_bundle.py` and `test_update_apply.py` against the patch, and the edited lines of `bundle.py` and `update.py` end to end: the guard refused a scratch copy of the tests outside this worktree, so those two paths are read, not run, and the build that follows runs them. The pending `RELEASE_YML_MANIFEST.diff` was read: it edits other lines of `release.yml`. |
| 7 | Your estimate of rounds, and whether it can merge beside PL4 and PL7d. | **Three build rounds, four if the first scan finds something.** The first of them builds the Dockerfile, the licence gate shown red, the constraints file, the renderer change (owned, no env file), `deploy/compose/dev.yaml`, the register rows, and the tests that name the pin (`tests/harness/test_render.py`, `test_cluster_render.py`, `tests/cli/test_images_verb.py`, the release-lock and signatures tests); the second is the verifier's findings and the live run on a lease (the live step is off, so each live test is owed and a release is refused until it has run: the key round trip and the usage test against the new image); a fourth only if trivy finds fixable HIGH or CRITICAL in what a fresh resolution installs. **Beside PL4:** yes, no shared file: PL4 is `apps/workspace` and `packages/design`, the build is `harness/`, `deploy/`, `tests/harness`, `tests/cli` and the register. **Beside PL7d:** it can be built beside it (different new files) but its merge order matters: both edit `harness/render.py`'s image list (different lines, 40 apart, which git merges) and both come with owner diffs to the same protected files (`release.yml`, `signatures.py`, the Core Makefile; the patch in row 6 also edits `bundle.py` and `update.py`, which PL7d's does not touch). **PL11 must merge first** for the register part (the register and `HELD_FOR_OWNER` exist only on its branch); if it has not, the build cannot remove the held name or add rows. | Read: `slices/PL7d.md` (its release.yml, signatures and Makefile diffs, its `pages` entry), `slices/PL4a.md` to `PL4d3e.md` headings (the workspace and design folders), PL11's branch (`git diff --stat` against main: the register tool `licence_register` (a module of PL11's branch, not on main), `tools/licence_check.py`, `harness/render.py`, `spec/LICENCE_REGISTER.yaml`). The estimate is mine, not measured. |
| 8 | If the gateway cannot run without the folder: say so plainly. | **It can run without the folder, and without the package.** Nothing here is a case of "cannot run": see rows 1 to 3. The caveat is the opposite one: the folder is not the only commercial content (row 9), so removing the folder alone would not make an image free of it. | Run: the three scratch gateways (a), (b), (c) and the repository's live round trip against (a) and (c). |
| 9 | Read the licence files inside the pinned image: the top-level LICENSE, the enterprise LICENSE, the directories the top-level file carves out, and any commercially licensed content elsewhere. | **The image has no `/app/LICENSE`.** The top-level file is `litellm-1.101.0.dist-info/licenses/LICENSE` inside the venv (identical text in `litellm-proxy-extras`). It says: "Portions of this software are licensed as follows: * All content that resides under the "enterprise/" directory of this repository, if that directory exists, is licensed under the license defined in "enterprise/LICENSE". * Content outside of the above mentioned directories or restrictions above is available under the MIT license as defined below." Then the MIT text, "Copyright (c) 2023 Berri AI". **It carves out one directory, `enterprise/`** (the "restrictions above" it also names are none: there is no second item). The carve-out names `enterprise/LICENSE`; the file is `enterprise/LICENSE.md`. `/app/enterprise/LICENSE.md` is the BerriAI Enterprise licence (full text below): production use only under the BerriAI Subscription Terms of Service or an enterprise licence "for the correct number of user seats", development and testing allowed without one, and "it is forbidden to copy, merge, publish, distribute, sublicense, and/or sell the Software". **Commercial content sits in three places, not one:** (1) `/app/enterprise/` (211 files: `litellm_enterprise/`, `enterprise_hooks/`, `enterprise_ui/`, `cloudformation_stack/`, and `dist/` holding 54 built archives of `litellm-enterprise` 0.1.1 to 0.1.32, 27 wheels and 27 sdists); (2) the installed package `/app/.venv/lib/python3.13/site-packages/litellm_enterprise/` (version 0.1.65, 142 Python files, its dist-info says `LicenseRef-Proprietary` and carries the same `LICENSE.md`); (3) nothing else of the publisher's. Searched the whole filesystem for the strings "BerriAI Enterprise", "Berrie AI", "LicenseRef-Proprietary" and the enterprise demo address: only those two trees and the MIT package's own upsell text and metadata. No vendored UI or proxy extra has a licence of its own: `litellm-proxy-extras` is MIT. Inside the MIT package, `litellm/proxy/enterprise_billing/billing_metrics.py` is code for a licensed deployment to push usage metrics to the publisher over mutual TLS; it is built only when `premium_user` is True and `LITELLM_BILLING_METRICS_ENDPOINT` and certificates are set (read, not run). 241 licence-named files in all; the Python packages declare MIT (74), Apache-2.0 (about 56), BSD (about 24), PSF, ISC, and **LGPL-3.0-only for `psycopg` and `psycopg-binary`**; three declare nothing in their metadata (`aurelio_sdk`, `google_crc32c`, `llm_sandbox`) and `detect-secrets` says UNKNOWN beside an Apache classifier; the 48 operating-system packages are MIT, BSD, Apache, MPL, PSF and GPL or LGPL (bash, busybox, glibc, libsndfile, libgcc, xz and others); none is commercial. The Prisma CLI inside is Apache-2.0. Full list by path below. | Read: the three licence files above in full, byte for byte (the two `LICENSE.md` copies are identical; checked with `diff`); every file in the exported filesystem whose name starts `LICENSE`, `COPYING`, `NOTICE` or `UNLICENSE` (241); every installed Python distribution's declared licence (110); the Wolfi package database (48 packages with their `L:` lines); a search of all text in the filesystem for the BerriAI strings above. The licence of the 48 operating-system packages and the three undeclared Python packages was **read from their metadata, not from their source**; whether those declarations are right is not checked. |

VERDICT: clean cut — the gateway starts and serves every route the product uses, and passes the repository's own real-gateway round trip, with `/app/enterprise` and the `litellm-enterprise` package both absent, every feature it uses is MIT code, and PyPI's own MIT files plus one uv override line build it without either.

## What this verdict is not

- **Not a built image.** Row 5 is a proposal. No Dockerfile was committed or built; the scratch images were `rm` of the publisher's, to measure behaviour, and are deleted. A derived image like that still ships the folder in its lower layers, which is why the build is made from PyPI's files in a fresh stage.
- **Not every test.** The CI conformance jobs (real Ollama and Whisper models), the Laurium live tests, the `pg_dump` test and Bedrock were not run, each for the reason in row 1. A round-2 live run on a lease is where they belong.
- **The default exclusion is a step, not a given.** `pip install "litellm[proxy]"` brings `litellm-enterprise` back; the override and the build-time licence gate are what keep it out, and the gate must be shown red.

## The licence texts, quoted in full

**`litellm-1.101.0.dist-info/licenses/LICENSE`** (the top-level file; there is no `/app/LICENSE`), before the MIT text:

```
Portions of this software are licensed as follows:

* All content that resides under the "enterprise/" directory of this repository, if that directory exists, is licensed under the license defined in "enterprise/LICENSE".
* Content outside of the above mentioned directories or restrictions above is available under the MIT license as defined below.
---
MIT License

Copyright (c) 2023 Berri AI
```

**`/app/enterprise/LICENSE.md`** (identical to `litellm_enterprise-0.1.65.dist-info/licenses/LICENSE.md`):

```
The BerriAI Enterprise license (the "Enterprise License")
Copyright (c) 2024 - present Berrie AI Inc.

With regard to the BerriAI Software:

This software and associated documentation files (the "Software") may only be
used in production, if you (and any entity that you represent) have agreed to,
and are in compliance with, the BerriAI Subscription Terms of Service, available
via [call](https://enterprise.litellm.ai/demo) or email (info@berri.ai) (the "Enterprise Terms"), or other
agreement governing the use of the Software, as agreed by you and BerriAI,
and otherwise have a valid BerriAI Enterprise license for the
correct number of user seats. Subject to the foregoing sentence, you are free to
modify this Software and publish patches to the Software. You agree that BerriAI
and/or its licensors (as applicable) retain all right, title and interest in and
to all such modifications and/or patches, and all such modifications and/or
patches may only be used, copied, modified, displayed, distributed, or otherwise
exploited with a valid BerriAI Enterprise license for the  correct
number of user seats.  Notwithstanding the foregoing, you may copy and modify
the Software for development and testing purposes, without requiring a
subscription.  You agree that BerriAI and/or its licensors (as applicable) retain
all right, title and interest in and to all such modifications.  You are not
granted any other rights beyond what is expressly stated herein.  Subject to the
foregoing, it is forbidden to copy, merge, publish, distribute, sublicense,
and/or sell the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

For all third party components incorporated into the BerriAI Software, those
components are licensed under the original license provided by the owner of the
applicable component.
```

## Licence-named files that matter, by path

| Path (inside the image) | SPDX identifier or first line | Commercial? |
| --- | --- | --- |
| `/app/.venv/lib/python3.13/site-packages/litellm-1.101.0.dist-info/licenses/LICENSE` | "Portions of this software are licensed as follows:" then MIT, Berri AI 2023 | No: MIT, with the `enterprise/` carve-out |
| `/app/litellm-proxy-extras/LICENSE` and the copy in `litellm_proxy_extras-0.4.94.dist-info/licenses/LICENSE` | Same text as above; the package declares `License-Expression: MIT` | No |
| `/app/enterprise/LICENSE.md` | "The BerriAI Enterprise license (the "Enterprise License")" | **Yes** |
| `/app/.venv/lib/python3.13/site-packages/litellm_enterprise-0.1.65.dist-info/licenses/LICENSE.md` | The same; the package declares `LicenseRef-Proprietary` | **Yes** |
| `/opt/prisma/binaries/node_modules/prisma/LICENSE` and the engines' | Apache-2.0 (Prisma 5.4.2) | No |
| `/usr/lib/python3.13/LICENSE.txt` | "A. HISTORY OF THE SOFTWARE" (PSF-2.0) | No |
| psycopg 3.3.3 and psycopg-binary 3.3.3 dist-info | LGPL-3.0-only | No (copyleft, OSI-approved) |
| the other 230-odd files | each package's own (MIT, Apache-2.0, BSD, MPL, PSF, ISC, zlib) | No |

## What I ran, exactly

Everything in `/tmp` and Docker, named `pl13-scout-<id>`; nothing in the repository or the home folder; the owner's `osprey-local-lite-*` containers, ports, volumes and network were not touched, and `make dev-up`, `ospreyflow start` and `docker compose` were not run. The master and salt keys of each gateway were made at run time (`openssl rand`), held in the shell and in that container's environment only, and the containers were removed. No hosted provider or real model was called: the stand-in upstreams answered.

1. `docker create` and `docker export` of the pinned image into a scratch folder; `docker rm`.
2. `docker build` of two scratch images from it (one `RUN rm -rf` each), removed after.
3. Per variant: one network, one `postgres:16.4`, one stand-in upstream (the pinned image's own Python), one gateway with the rendered config, port `127.0.0.1:` ephemeral; the 24-call script; the container logs read; all removed.
4. The repository's `test_model_gateway_live.py` through pytest against (a) and (c).
5. `git archive` of `lane/slice-AD1a` into a scratch folder and pytest there; pytest on this worktree for the main-side files.
6. `uv venv` and `uv pip install` into a scratch environment; PyPI's JSON, sdist and one wheel downloaded and hash-checked.

## How this file was made

**Correction after the verifier's finding.** The verifier found that the first draft's `signatures.py` diff (one line, `litellm` added to
`OPTIONAL_OWNED_SERVICES`) would have refused every older lock, because those name the publisher's gateway under the same
service name `litellm`; its comment ("a lock from before names the publisher's image, a third party's, and none of it is checked") was wrong. Confirmed by reading
`render.py` 1844-1855, `owned_references`, `bundle.py` 320 and `update.py` 368-369, and by running the one-line change in
memory against an older lock (refused, red) and the replacement (verifies, green). The patch now checks the repository as well
as the name, in all three places that used the name alone. Rows 1 to 5 and 7 to 9 are unchanged and stand on the earlier
sessions' runs.

An earlier session of this slice drafted it in scratch and stopped before committing. This session re-read, from the
pinned image's exported filesystem, the top-level `LICENSE`, the enterprise `LICENSE.md` (and checked the two copies are
identical), the import lines in `proxy_server.py` and `proxy/hooks/__init__.py`, the `litellm` and `litellm-enterprise`
metadata, and the 211 files under `/app/enterprise`; read the earlier session's scratch logs for the live usage test (passed
against variants (a) and (c)); and re-ran `git apply --check` on the patch below against main (c71c727). It corrected one
quotation (the enterprise licence's last sentence). The three-gateway route runs in row 1 were **not re-run** in this
session; they stand on the earlier session's scratch logs, which were read.

## The protected-file diffs (two patches for the owner to apply; each passes `git apply --check` against main on its own, c71c727, whose five files are identical on aad2df3)

**Patch 1 (signature check) may be applied at any time**, alone: it is safe before or after the build and the render switch (row 6). **Patch 2 (release matrix and Core Makefile) must wait until round 2's `deploy/litellm/Dockerfile` is on main**: applied earlier it fails `make ci` (a `docker build` of a missing Dockerfile) and the next release. The two patches touch different files, so either leaves the other applicable.

### Patch 1: signature check (apply at any time)

```diff
diff --git a/OspreyFlow_Core/harness/signatures.py b/OspreyFlow_Core/harness/signatures.py
--- a/OspreyFlow_Core/harness/signatures.py
+++ b/OspreyFlow_Core/harness/signatures.py
@@ -54,9 +54,14 @@
 #: is a third party's, except those below.
 OWNED_SERVICES = ("workspace", "api", "ingest", "ner")
 #: Built and signed by the release too, and checked whenever a lock names them: Superset, which a
-#: release's lock names from build order step 20a on (a lock from before names none).
-OPTIONAL_OWNED_SERVICES = ("superset",)
+#: release's lock names from build order step 20a on (a lock from before names none), and the model
+#: gateway (PL13), which a release's lock names as ours from the release that first builds it.
+OPTIONAL_OWNED_SERVICES = ("superset", "litellm")
 SIGNED_SERVICES = OWNED_SERVICES + OPTIONAL_OWNED_SERVICES
+#: Every lock before PL13 names the publisher's gateway image under the service name `litellm`: a
+#: third party's image, never signed by our release. The name alone cannot tell it from ours, so an
+#: entry is checked only if its repository is not under one of these.
+THIRD_PARTY_REPOSITORIES = ("ghcr.io/berriai/",)
 _DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
 
 Run = Callable[[Sequence[str]], tuple[int, str]]
@@ -224,6 +229,12 @@
             )
 
 
+def is_signed_image(service: object, repository: object) -> bool:
+    """Whether a lock entry is an image our release signs: a signed service whose repository is not
+    a third party's (the publisher's gateway, which older locks name as `litellm`)."""
+    return service in SIGNED_SERVICES and not str(repository).startswith(THIRD_PARTY_REPOSITORIES)
+
+
 def owned_references(lock_text: str) -> list[str]:
     """`repository@digest` of each owned image in a lock, in the lock's order (an optional one,
     Superset, whenever the lock names it). An owned image with no real digest, or one of
@@ -236,7 +247,7 @@
     refs = []
     for entry in entries:
         service = entry.get("service")
-        if service not in SIGNED_SERVICES:
+        if not is_signed_image(service, entry.get("repository")):
             continue
         digest = str(entry.get("digest"))
         if not _DIGEST.match(digest):
diff --git a/OspreyFlow_Core/harness/bundle.py b/OspreyFlow_Core/harness/bundle.py
--- a/OspreyFlow_Core/harness/bundle.py
+++ b/OspreyFlow_Core/harness/bundle.py
@@ -47,9 +47,9 @@
 from harness.signatures import (
     COSIGN_IMAGE_IDS,
     COSIGN_PLATFORM_IMAGES,
-    SIGNED_SERVICES,
     Cosign,
     Identity,
+    is_signed_image,
 )
 
 BUNDLE_FORMAT = 1
@@ -317,7 +317,7 @@
             )
         layout = root / str(item["saved"])
         config = _manifest_config(layout, digest, repository, platform)
-        if entry.get("service") in SIGNED_SERVICES:
+        if is_signed_image(entry.get("service"), repository):
             ok, said = cosign.verify_local(layout, identity)
             if not ok:
                 last = said.splitlines()[-1] if said else "no answer"
diff --git a/OspreyFlow_Core/harness/update.py b/OspreyFlow_Core/harness/update.py
--- a/OspreyFlow_Core/harness/update.py
+++ b/OspreyFlow_Core/harness/update.py
@@ -56,6 +56,7 @@
 )
 from harness.signatures import (
     SIGNED_SERVICES,
+    THIRD_PARTY_REPOSITORIES,
     Cosign,
     Identity,
     Keyless,
@@ -365,8 +366,10 @@
         name = str(row.get("Service"))
         image = (services.get(name) or {}).get("image", "")
         repository = _repository(str(image))
-        if repository not in digests or not any(
-            repository.endswith(f"/{s}") for s in SIGNED_SERVICES
+        if (
+            repository not in digests
+            or repository.startswith(THIRD_PARTY_REPOSITORIES)
+            or not any(repository.endswith(f"/{s}") for s in SIGNED_SERVICES)
         ):
             continue
         image_id = _ok(
```

### Patch 2: release matrix and Core Makefile (apply only after `deploy/litellm/Dockerfile` is on main)

```diff
diff --git a/OspreyFlow_Core/.github/workflows/release.yml b/OspreyFlow_Core/.github/workflows/release.yml
--- a/OspreyFlow_Core/.github/workflows/release.yml
+++ b/OspreyFlow_Core/.github/workflows/release.yml
@@ -63,6 +63,9 @@
           - { service: report-sync, dockerfile: services/report_sync/Dockerfile }
           # Built from its own folder, not the repository root.
           - { service: superset, dockerfile: deploy/superset/Dockerfile, context: deploy/superset }
+          # PL13: the model gateway, built from the MIT code alone: the publisher's commercially licensed
+          # folder and package are never in it. Scanned and signed below like every image here.
+          - { service: litellm, dockerfile: deploy/litellm/Dockerfile, context: deploy/litellm }
     steps:
       - uses: actions/checkout@v4
       - uses: docker/login-action@v3
diff --git a/OspreyFlow_Core/Makefile b/OspreyFlow_Core/Makefile
--- a/OspreyFlow_Core/Makefile
+++ b/OspreyFlow_Core/Makefile
@@ -1,4 +1,4 @@
-.PHONY: check lint typecheck no-react-check version-isolation-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness trivy-image-ner trivy-image-worker trivy-image-report-sync trivy-image-superset trivy-image-laurium test-js dev-up dev-down docker-clean glass-perf glass-a11y glass-keyboard glass-map-verify glass-live harness-keyboard harness-a11y
+.PHONY: check lint typecheck no-react-check version-isolation-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness trivy-image-ner trivy-image-worker trivy-image-report-sync trivy-image-superset trivy-image-laurium trivy-image-litellm test-js dev-up dev-down docker-clean glass-perf glass-a11y glass-keyboard glass-map-verify glass-live harness-keyboard harness-a11y
 
 # The day's stamp each image's upgrade layer is keyed on (`harness/upgrade_stamp.py`, v0.6.0): an
 # upgrade layer is made again each day, never kept from a builder's cache.
@@ -10,7 +10,7 @@
 # What runs from this folder alone (`06_DECISIONS.md` ADR-114 Amendment 2). The specification's own
 # gates and the test suites are the developer repository's, in its Makefile; its `ci` runs this
 # `check` first. A user of this repository needs nothing from it.
-check: lint typecheck no-react-check version-isolation-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness trivy-image-ner trivy-image-worker trivy-image-report-sync trivy-image-superset trivy-image-laurium harness-a11y
+check: lint typecheck no-react-check version-isolation-check trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness trivy-image-ner trivy-image-worker trivy-image-report-sync trivy-image-superset trivy-image-laurium trivy-image-litellm harness-a11y
 
 lint:
 	$(RUFF) check .
@@ -92,6 +92,12 @@
 trivy-image-laurium:
 	docker build --pull --build-arg OSPREY_UPGRADE_STAMP=$(UPGRADE_STAMP) -f services/laurium/Dockerfile -t ospreyflow/laurium:ci services/laurium
 	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/laurium:ci
+
+# PL13: the model gateway, built from the MIT code alone (the publisher's commercially licensed folder and
+# package are never in it), scanned as every image of ours.
+trivy-image-litellm:
+	docker build --pull --build-arg OSPREY_UPGRADE_STAMP=$(UPGRADE_STAMP) -f deploy/litellm/Dockerfile -t ospreyflow/litellm:ci deploy/litellm
+	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/litellm:ci
 
 # Install, start, stop and update the deployment with the `ospreyflow` command (`cli/`; ADR-114):
 # `ospreyflow install --mode lite`, `ospreyflow start [--build]`, `ospreyflow status`, `ospreyflow open`.
```
