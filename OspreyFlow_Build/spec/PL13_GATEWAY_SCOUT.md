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
| 2 | Does the open-source code import anything from `/app/enterprise` at start-up or on any route the product uses? Name each import. | **Yes, three imports of the folder, all swallowed when it is absent; and about thirty imports of the installed `litellm_enterprise` package, all of them inside a `try` except one, on a route the product does not use.** The folder: (i) litellm/proxy/proxy_server.py line 782 `from litellm.proxy import enterprise` then line 786 `import enterprise`, at start-up, in `try ... except Exception: pass` (loads a 16-byte `__init__.py`); (ii) litellm/proxy/hooks/__init__.py line 49 `from enterprise.enterprise_hooks import ENTERPRISE_PROXY_HOOKS`, at start-up, in `except ImportError`, which adds two hooks, `managed_files` and `managed_vector_stores` (LiteLLM's own managed-files API: the product uses neither); (iii) litellm/proxy/management_endpoints/customer_endpoints.py line 217 `from enterprise.enterprise_hooks.blocked_user_list`, only on `/customer/block` (answers 400 when absent; not used). The folder's own `enterprise_hooks/__init__.py` imports from the *package*, not from the folder's code. The package, at start-up, each in `try` and `except`: proxy_server.py 793-794 (routes and `EnterpriseProxyConfig`), litellm_core_utils/litellm_logging.py 206-221, proxy/utils.py 46-55, proxy/auth/user_api_key_auth.py 111; on a route, each guarded: proxy/auth/route_checks.py 77 (every management route; `except Exception: pass`), key_management_endpoints.py 1096 (every `/key/generate`), key_management_event_hooks.py 419-537 (email on key events), proxy_server.py 9779 and 9810 (batch polling jobs), public_endpoints.py 355. Config-gated and not in the renderer's config: callback_utils.py 187-296 (seven named callbacks), guardrail_initializers.py 149, custom_guardrail.py 1000 and 1027 (each caught as `ImportError` and then re-raised as an `ImportError` when a guardrail uses a tag-based mode, so that one guardrail would fail, and none is configured), custom_logger_registry.py 114-123. Also on a route, each caught as `ImportError`: user_management_event_hooks.py 130 (invitation email), ui_sso.py 1081 (a custom SSO handler, only if one is set). **Exactly one import has no handler for the error: response_api_endpoints/endpoints.py 371** (Responses API with `background=true`; its `try` catches only the guardrail's own exception, so an absent package would fail that one request; the product does not use the Responses API). An earlier draft said "two"; a second pass over all 47 hits in the PyPI wheel found one. Measured: with both gone `proxy_server` imports, `enterprise_proxy_config` is None, `premium_user` is False, and the 24 calls in row 1 are unchanged. | Read: every match of `litellm_enterprise`, `from enterprise`, `import enterprise` and `enterprise_hooks` in the installed litellm (47 hits in 18 files), each with its surrounding lines; re-read a second time from PyPI's own wheel (the same 47 lines), each handler checked again; `docker/Dockerfile` at the image's revision (its own comment: "enterprise/ is imported by source path at runtime"). Run: an in-image probe of what a console script sees (`/app` reaches `sys.path` through litellm's own `prisma_migration.py` line 13, so `import enterprise` succeeds at start-up in the shipped image) and, in variant (c), `find_spec` for both names (both absent, `PackageNotFoundError` for the metadata). |
| 3 | Does building from the MIT source, or installing the package, pull in `litellm-enterprise`? How is it excluded, and does anything break? | **Yes, by default, and it is proprietary.** litellm 1.101.0's `proxy` extra has the hard line `Requires-Dist: litellm-enterprise==0.1.65 ; extra == 'proxy'` (METADATA line 62; PyPI's own JSON for 1.101.0 says the same), and `litellm-enterprise` 0.1.65 declares `License-Expression: LicenseRef-Proprietary` (its METADATA, its pyproject, and PyPI's record). The pinned image carries it twice: as the folder and as the installed package (142 Python files, from `file:///app/enterprise`). **The PyPI sdist (3434 files) and wheel (3260 files) of litellm 1.101.0 contain no `enterprise/` folder at all.** Exclusion that works: a uv override file with the one line `litellm-enterprise ; python_version < "0"`. Resolved with `uv pip compile` (the package is gone from the 340-line result, `litellm-proxy-extras==0.4.94`, which is MIT, stays) and installed for real into a scratch virtual environment (112 packages): `litellm_enterprise` and `enterprise` are not importable, `uv pip check` reports "All installed packages are compatible", `proxy_server` imports, `enterprise_proxy_config` is None, `premium_user` is False. Nothing breaks: see rows 1 and 2. **Do not derive from the publisher's image**: a later `rm` hides the folder but its layers stay in the image and are still shipped; build from PyPI's files in a fresh stage. | Read: `litellm-1.101.0.dist-info/METADATA` in the image, `litellm_enterprise-0.1.65.dist-info/METADATA` and `direct_url.json`, `enterprise/pyproject.toml`, PyPI JSON for litellm 1.101.0, litellm-enterprise 0.1.65 and litellm-proxy-extras 0.4.94. Run: downloaded the sdist and one wheel and checked their SHA-256 against PyPI's (734ab2b8... for the sdist), listed both; `uv pip compile` with and without the override; `uv venv` and `uv pip install` of `litellm[proxy]==1.101.0` with the override; `uv pip check`. The image's litellm package is byte-identical to the PyPI wheel (3254 of 3255 files; the one difference, `rust_bridge/_native.abi3.so`, is a compiled file for another CPU, and I compared an x86-64 wheel with an arm64 layer). |
| 4 | Which gateway features does OspreyFlow use, and is each in the MIT code? | **Every one is in the MIT package; none is behind the publisher's licence key.** Used: the master key; virtual keys, one per hosted engine (`/key/generate`, `/key/update`, `/key/delete`, `/key/list`) with `models`, `rpm_limit`, `tpm_limit`, `max_budget`, `budget_duration` and `metadata`; budgets and rate limits per key; routing from `litellm.yaml` (`ollama_chat`, `ollama` and an OpenAI-compatible route) and entries made at run time (`/model/new`, `/model/delete`, `/v2/model/info`, `store_model_in_db`); named credentials (`/credentials` create, read by name, delete); a per-call tag in the request's `metadata.tags` read back by `/tag/daily/activity`; chat, embeddings and transcription; Postgres through Prisma (`litellm-proxy-extras`, MIT); `/health/liveliness`; the AWS IAM route for Bedrock. Not used: teams, users, the admin UI, SSO, guardrails, callbacks, alerting, email, the Responses API, key `tags`. **The publisher's licence gate (`premium_user`, read from `LITELLM_LICENSE`) is itself MIT code** and guards, among others, key `tags` (line 1181), `model_max_budget` (7082), key regeneration, `/spend/report` and wildcard model access groups: the product uses none of them, sets no `LITELLM_LICENSE`, and every call above worked with `premium_user` False. A tag-based spend read is not gated (it worked unlicensed). | Read: `packages/adapters/model_litellm/client.py`, `usage.py`, `stand_in.py`'s header, `services/api/model_admin.py` (`add_entry`, `put_credential`, `put_engine_key`, `key_limits`, the key listing), the rendered `litellm.yaml` (`render_litellm_config`'s own output, saved and used for every run), `harness/render.py`'s `litellm` service. Searched for `premium_user` and `_premium_user_check` in the key, model, credential, tag and spend endpoint files. Run: the 24 calls and the live round trip. Each route's handler was found in the PyPI wheel. Not run: the Bedrock IAM route (no AWS account), the admin UI, any hosted provider. |
| 5 | The smallest build: base image, pinned version, what the Dockerfile copies, how the pin is recorded in the register and `versions.lock`. | **Proposal for the build, not built.** Base: the publisher's own, `cgr.dev/chainguard/wolfi-base@sha256:e624c5d5e42382ce7165ddafcbbf8e6769a24cbd02ea6114b880b05ae5ba2a8d` (read from its Dockerfile at revision 18243cd7; every measurement in ADR-135 was taken on it), with `apk add bash openssl tzdata nodejs python-3.13 libsndfile` (48 packages, none commercial). Pin: `litellm==1.101.0` and `litellm-proxy-extras==0.4.94` from PyPI, extras as the pinned image (`proxy`, `proxy-runtime`, `extra_proxy`, `semantic-router`, `saml`, `bedrock-realtime`; trimming them is a later, measured choice), the versions of every other package held by a constraints file made from the pinned image's own venv, `litellm-enterprise` removed by the override in row 3. A builder stage installs; the runtime stage copies only: the venv, `docker/` (the two entrypoint scripts), `schema.prisma`, `prisma_migration.py` and `/opt/prisma` (the Prisma CLI and engines, which need the network at build time). **It never copies `/app/enterprise`.** A build-time licence gate (the `ner` image has one: `services/ner/licence_gate.py`) must fail on `litellm-enterprise` or any proprietary licence and be shown red by installing it (rule 15). **Register** (PL11's `spec/LICENCE_REGISTER.yaml` and the register tool `licence_register` (a module of PL11's branch, not on main) are on branch `lane/slice-PL11`, **not merged**, not on main): remove `ghcr.io/berriai/litellm` from `HELD_FOR_OWNER`, and add rows for each new `FROM` (the wolfi base, the uv image) with the licence read at the pin; the gate reads every Dockerfile under the product folder and fails on a base with no row. **`versions.lock`**: no change to `harness/release_lock.py`: once `harness/render.py` names the gateway as an owned image it appears in the lock as `repository@digest` with its tag the commit and its source the registry, as the other owned images do. **Two things found by reading that the build must handle:** `ServiceImage.owned` also gives a service `env_file: deployment.env` (render.py line 1039), which would hand the gateway the whole deployment's secrets, so the gateway needs "built by us, no env file" with a test; and the pin sits in four more places: `deploy/compose/dev.yaml` line 290 (the test `test_the_rendered_model_proxy_is_the_developer_stacks` holds the two equal), `.github/workflows/ci.yml` lines 980 and 1032 (protected: a diff), the cloud-platform manifest and the administration guide. | Read: `harness/render.py` (lines 631-684, 914-948, 1039, 1536-1590, 1798-1860), `harness/images.py` (`ServiceImage`), `harness/release_lock.py`, `harness/signatures.py`, `harness/bundle.py`, `harness/update.py`, the publisher's `Dockerfile` at revision 18243cd7 (fetched), `docker history` of the pinned image, PL11's register and the register tool `licence_register` (a module of PL11's branch, not on main) (read with `git show` from its branch). Run: the uv override (row 3). **Not run:** any Docker build of the proposed Dockerfile (the build that follows this scout), a trivy scan of it (the scan belongs to that build, and a fresh resolution may find fixable HIGH or CRITICAL findings the pinned image does not carry). |
| 6 | Protected files a release of the new image would touch, as diffs that pass `git apply --check`. | **Five files, in two patches with different timing.** **Patch 1, safe to apply at any time** (before or after the build, and before or after the render switch): `harness/signatures.py`, `harness/bundle.py` and `harness/update.py`, below. **Patch 2, apply only once the build's `deploy/litellm/Dockerfile` is on main** (the build is a later round; the path is a proposal and no such file exists today): `release.yml` and the Core Makefile. Applied before that file exists, patch 2 turns `make ci` red for every merge (Core's `check` would run `docker build -f deploy/litellm/Dockerfile`, and Build's `ci` runs Core's `check` first) and fails the next tagged release's matrix job the same way. `OspreyFlow_Core/.github/workflows/release.yml` (patch 2): one new matrix entry after the superset line (about line 65); the scan (trivy at lines 87-94), the push, the keyless signing and the lock verification are all driven by the matrix, so they need no other change. `OspreyFlow_Core/Makefile` (patch 2): `trivy-image-litellm` added to the `.PHONY` line (1), to `check` (13), and as a target after `trivy-image-laurium` (92-94). **The signature check needs more than one line, because every lock to date names the publisher's gateway under the service name `litellm`** (`_render_versions_lock`, `harness/render.py` 1844-1855 writes `service: litellm`, `repository: ghcr.io/berriai/litellm`, a real digest). Adding `litellm` to `OPTIONAL_OWNED_SERVICES` alone (this file's first draft) would hand that image to `cosign verify` against OspreyFlow's release workflow, which it can never pass, so every older lock, every older bundle and main's own next release would be refused. Measured in memory with a fake cosign that refuses what is not ours: the one-line change refuses the older lock (5 images checked, the publisher's among them); main as it is, and the patch below, verify it (4 checked). **Patch 1:** `harness/signatures.py` adds `litellm` to `OPTIONAL_OWNED_SERVICES`, a `THIRD_PARTY_REPOSITORIES = ("ghcr.io/berriai/",)` and one predicate `is_signed_image(service, repository)` (a signed service **and** a repository not under a third party's) that `owned_references` now uses. `harness/bundle.py` line 320 (`entry.get("service") in SIGNED_SERVICES`, the offline check of a bundle) and `harness/update.py` lines 368-369 (`repository.endswith(f"/{s}")`, the check of what is running) each had their own name-only copy of the test and use the new rule too. **Patch 1 is safe in any order against the render switch:** before the build names our gateway no lock entry changes meaning; after it, `ghcr.io/<owner>/litellm` is checked and, unsigned, is refused (shown in memory). **The build that follows commits these tests with it, each shown red against the one-line change:** an older lock naming `ghcr.io/berriai/litellm` under `litellm` is not in `owned_references` and `verify_release` passes it with a cosign that refuses it; `make_bundle`'s offline check and `verify_running` skip it; a lock naming `ghcr.io/<owner>/litellm` unsigned is refused by name. Also protected: `.github/workflows/ci.yml` lines 980 and 1032 (the conformance jobs run the publisher's image; they move to ours once it exists): **no diff yet, it is written in the build, and it waits for our image to be on the registry**, so it has patch 2's timing, never earlier. The two patches are in the last section and each passes `git apply --check` against main on its own; the Dockerfile path patch 2 names, `deploy/litellm/Dockerfile`, is a proposal. **They touch the same lines PL7d's diffs will** (the matrix anchor, the `OPTIONAL_OWNED_SERVICES` line, the target block): the owner applies one and the other is rewritten against the new main. | Read: `release.yml` in full (187 lines), `signatures.py` in full, `bundle.py` 300-335, `update.py` 320-385, `images.py`, `release_lock.py`, `render.py` 1835-1865, the Makefile lines 1, 13 and 91-95, `tests/harness/test_signatures.py` (its `_lock` helper and the Superset case, which the new cases copy). Run: a script (a heredoc; no file written) took each file's text from `git show HEAD:<path>`, made the edits, built the diff with `difflib` and ran `git apply --check` on it (passed; base c71c727, and the five files' blobs are identical on main aad2df3); ran `ruff check` and `ruff format --check` on each patched file from stdin (check clean; `bundle.py` was not format-clean before and is no worse); split the patch by file into the two patches below and ran `git apply --check` on each alone and on both together (all pass, against this branch's tip and against main aad2df3, whose five files are the same blobs); and loaded the unpatched, the one-line and the patched `signatures.py` in memory to run `verify_release` on an older and on a new lock. **Not run:** the existing `test_bundle.py` and `test_update_apply.py` against the patch, and the edited lines of `bundle.py` and `update.py` end to end: the guard refused a scratch copy of the tests outside this worktree, so those two paths are read, not run, and the build that follows runs them. The pending `RELEASE_YML_MANIFEST.diff` was read: it edits other lines of `release.yml`. |
| 7 | Your estimate of rounds, and whether it can merge beside PL4 and PL7d. | **Three build rounds, four if the first scan finds something.** The first build step builds the Dockerfile, the licence gate shown red, the constraints file, the renderer change (owned, no env file), `deploy/compose/dev.yaml`, the register rows, and the tests that name the pin (`tests/harness/test_render.py`, `test_cluster_render.py`, `tests/cli/test_images_verb.py`, the release-lock and signatures tests); the second is the verifier's findings on the first; the third is the live run on a lease (the live step is off, so each live test is owed and a release is refused until it has run: the key round trip and the usage test against the new image); a fourth only if trivy finds fixable HIGH or CRITICAL in what a fresh resolution installs. **Beside PL4:** yes, no shared file: PL4 is `apps/workspace` and `packages/design`, the build is `harness/`, `deploy/`, `tests/harness`, `tests/cli` and the register. **Beside PL7d:** it can be built beside it (different new files) but its merge order matters: both edit `harness/render.py`'s image list (different lines, 40 apart, which git merges) and both come with owner diffs to the same protected files (`release.yml`, `signatures.py`, the Core Makefile; the patch in row 6 also edits `bundle.py` and `update.py`, which PL7d's does not touch). **PL11 must merge first** for the register part (the register and `HELD_FOR_OWNER` exist only on its branch); if it has not, the build cannot remove the held name or add rows. | Read: `slices/PL7d.md` (its release.yml, signatures and Makefile diffs, its `pages` entry), `slices/PL4a.md` to `PL4d3e.md` headings (the workspace and design folders), PL11's branch (`git diff --stat` against main: the register tool `licence_register` (a module of PL11's branch, not on main), `tools/licence_check.py`, `harness/render.py`, `spec/LICENCE_REGISTER.yaml`). The estimate is mine, not measured. |
| 8 | If the gateway cannot run without the folder: say so plainly. | **It can run without the folder, and without the package.** Nothing here is a case of "cannot run": see rows 1 to 3. The caveat is the opposite one: the folder is not the only commercial content (row 9), so removing the folder alone would not make an image free of it. | Run: the three scratch gateways (a), (b), (c) and the repository's live round trip against (a) and (c). |
| 9 | Read the licence files inside the pinned image: the top-level LICENSE, the enterprise LICENSE, the directories the top-level file carves out, and any commercially licensed content elsewhere. | **The image has no `/app/LICENSE`.** The top-level file is `litellm-1.101.0.dist-info/licenses/LICENSE` inside the venv (identical text in `litellm-proxy-extras`). It says: "Portions of this software are licensed as follows: * All content that resides under the "enterprise/" directory of this repository, if that directory exists, is licensed under the license defined in "enterprise/LICENSE". * Content outside of the above mentioned directories or restrictions above is available under the MIT license as defined below." Then the MIT text, "Copyright (c) 2023 Berri AI". **It carves out one directory, `enterprise/`** (the "restrictions above" it also names are none: there is no second item). The carve-out names `enterprise/LICENSE`; the file is `enterprise/LICENSE.md`. `/app/enterprise/LICENSE.md` is the BerriAI Enterprise licence (full text below): production use only under the BerriAI Subscription Terms of Service or an enterprise licence "for the correct number of user seats", development and testing allowed without one, and "it is forbidden to copy, merge, publish, distribute, sublicense, and/or sell the Software". **Commercial content sits in two places, not one:** (1) `/app/enterprise/` (211 files: `litellm_enterprise/`, `enterprise_hooks/`, `enterprise_ui/`, `cloudformation_stack/`, and `dist/` holding 54 built archives of `litellm-enterprise` 0.1.1 to 0.1.32, 27 wheels and 27 sdists); (2) the installed package `/app/.venv/lib/python3.13/site-packages/litellm_enterprise/` (version 0.1.65, 142 Python files, its dist-info says `LicenseRef-Proprietary` and carries the same `LICENSE.md`). There is no third place. Searched the whole filesystem for the strings "BerriAI Enterprise", "Berrie AI", "LicenseRef-Proprietary" and the enterprise demo address: only those two trees and the MIT package's own upsell text and metadata. No vendored UI or proxy extra has a licence of its own: `litellm-proxy-extras` is MIT. Inside the MIT package, `litellm/proxy/enterprise_billing/billing_metrics.py` is code for a licensed deployment to push usage metrics to the publisher over mutual TLS; it is built only when `premium_user` is True and `LITELLM_BILLING_METRICS_ENDPOINT` and certificates are set (read, not run). **242 licence-named files in all** (list 1 below, each with its path and its SPDX identifier or first line) and **193 installed Python distributions** (list 2, each with the licence its own metadata declares); the earlier drafts' "241" left out one `COPYRIGHT.txt` and their "110" distributions was a wrong count. What the lists show: **commercial: the two enterprise trees (two `LICENSE.md` copies) and nothing else**; **LGPL-3.0-only** for `psycopg` and `psycopg-binary` (copyleft, not commercial); `litellm-enterprise` is the one distribution declaring `LicenseRef-Proprietary`. **The three that declare nothing in their metadata each carry a licence file, read:** `aurelio_sdk` 0.0.19 (`LICENSE`, first line "MIT License"), `google_crc32c` 1.8.0 (`LICENSE`, "Apache License") and `llm_sandbox` 0.3.39 (`LICENSE`, "MIT License"). `detect-secrets` 1.5.0 has `UNKNOWN` in its licence field, the Apache classifier and a `LICENSE` that opens "Apache License". Two distributions have no licence file in the image (`opentelemetry-util-http` 0.49b0 and `tokenizers` 0.23.1) and declare Apache-2.0 / the Apache classifier in their metadata: that declaration is all there is, not checked against their source. **Text of every one of the 242 files was searched** for "enterprise license", "subscription terms", "proprietary", "may only be used in production", "valid ... licence", "Berri", "LiteLLM", "non-commercial", "trial" and "evaluation": the hits are the two enterprise `LICENSE.md` copies, the three MIT copies of the top-level file (the Berri AI copyright line), the `email_validator` public-domain dedication ("commercial or non-commercial") and the GPL text numpy quotes for a bundled component ("proprietary"); none restricts use. A broader search ("commercial", "all rights reserved", "not distributed") hit 134 files; the matched line of each was read: the two enterprise files, and otherwise only the Apache-2.0 disclaimer ("any and all other commercial damages"), BSD notices ("All rights reserved") and the MPL-2.0 header ("not distributed with this file"). The **48 operating-system packages** (list 3) declare MIT (16), LGPL-2.1-or-later (6), GPL-3.0-or-later (4 and others with it), MPL-2.0 with MIT (3), Apache-2.0 (3), BSD (several), GPL-2.0-only (2), PSF-2.0 (2) and a few other open licences (`blessing`, `CC-PDDC`): GPL or LGPL for bash, busybox, glibc, libgcc, xz and others; none is commercial. The Prisma CLI and engines (`/opt/prisma`) are Apache-2.0 files. **Not read:** the source of any package against its declared licence, and the operating-system packages' licence texts (only `opus` and `mpdecimal` carry a file; the other 46 are the database's word). | Run: `docker create` and `docker export` of the pinned image (by digest) into a scratch folder of its own, one container `pl13-scout-<id>`, removed; no container started. Read: the three licence files in full, byte for byte (the two `LICENSE.md` copies are identical, checked with `diff` in the first session); every file in the exported filesystem whose name is `LICENSE`, `LICENCE`, `COPYING`, `NOTICE`, `UNLICENSE` or `COPYRIGHT` with any extension or a `LICENSE-` / `LICENSE.` prefix (242, symbolic links not followed), each opened for its SPDX line or first line; the `METADATA` of all 193 installed Python distributions; the 48 `L:` lines of `/lib/apk/db/installed`; a text search of all 242 files with the two patterns above; a search of all text in the filesystem for the BerriAI strings (first session). The scan scripts were kept outside the exported folder and run with `python3 -I`. |

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

## The whole-image licence list (question 9), as read in this round

The image's filesystem was exported to a scratch folder and walked (`/proc`, `/sys` and `/dev` hold nothing in an export and were skipped). Three lists, each complete for what it names. In list 1, `$SP` stands for `/app/.venv/lib/python3.13/site-packages`; every other path is whole. Symbolic links were not followed or counted.

### List 1: every file named `LICENSE`, `LICENCE`, `COPYING`, `NOTICE`, `UNLICENSE` or `COPYRIGHT` (with any extension, or a `LICENSE-` or `LICENSE.` prefix): 242 files, each with its path and its SPDX identifier (where the file carries one) or its first non-blank line

```text
$SP/a2a_sdk-1.1.0.dist-info/licenses/LICENSE | Apache License
$SP/aiofiles-24.1.0.dist-info/licenses/LICENSE | Apache License
$SP/aiofiles-24.1.0.dist-info/licenses/NOTICE | Asyncio support for files
$SP/aiohappyeyeballs-2.6.1.dist-info/LICENSE | A. HISTORY OF THE SOFTWARE
$SP/aiohttp-3.14.3.dist-info/licenses/LICENSE.txt | Apache License
$SP/aiohttp-3.14.3.dist-info/licenses/vendor/llhttp/LICENSE | MIT License
$SP/aiosignal-1.4.0.dist-info/licenses/LICENSE | Apache License
$SP/annotated_doc-0.0.4.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/annotated_types-0.7.0.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/anthropic-0.84.0.dist-info/licenses/LICENSE | Copyright 2023 Anthropic, PBC.
$SP/anyio-4.13.0.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/apscheduler-3.11.2.dist-info/licenses/LICENSE.txt | This is the MIT license: http://www.opensource.org/licenses/mit-license.php
$SP/asgiref-3.11.1.dist-info/licenses/LICENSE | Copyright (c) Django Software Foundation and individual contributors.
$SP/attrs-26.1.0.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/aurelio_sdk-0.0.19.dist-info/LICENSE | MIT License
$SP/aws_sdk_bedrock_runtime-0.7.0.dist-info/licenses/LICENSE | Apache License
$SP/aws_sdk_bedrock_runtime-0.7.0.dist-info/licenses/NOTICE | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
$SP/aws_sdk_signers-0.3.0.dist-info/licenses/NOTICE | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
$SP/awscrt-0.32.2.dist-info/licenses/LICENSE | Apache License
$SP/awscrt-0.32.2.dist-info/licenses/NOTICE | SPDX Apache-2.0.
$SP/azure_ai_contentsafety-1.0.0.dist-info/LICENSE | Copyright (c) Microsoft Corporation.
$SP/azure_core-1.41.0.dist-info/licenses/LICENSE | Copyright (c) Microsoft Corporation.
$SP/azure_identity-1.25.2.dist-info/licenses/LICENSE | Copyright (c) Microsoft Corporation.
$SP/azure_keyvault_secrets-4.10.0.dist-info/LICENSE | Copyright (c) Microsoft Corporation.
$SP/azure_storage_blob-12.28.0.dist-info/licenses/LICENSE | Copyright (c) Microsoft Corporation.
$SP/azure_storage_file_datalake-12.20.0.dist-info/LICENSE | Copyright (c) Microsoft Corporation.
$SP/backoff-2.2.1.dist-info/LICENSE | The MIT License (MIT)
$SP/boto3-1.43.1.dist-info/LICENSE | Apache License
$SP/boto3-1.43.1.dist-info/NOTICE | boto3
$SP/botocore-1.43.6.dist-info/LICENSE.txt | Apache License
$SP/botocore-1.43.6.dist-info/NOTICE | Botocore
$SP/bytecode-0.17.0.dist-info/licenses/COPYING | The MIT License (MIT)
$SP/certifi-2026.4.22.dist-info/licenses/LICENSE | This package contains a modified version of ca-bundle.crt:
$SP/cffi-2.0.0.dist-info/licenses/LICENSE | Except when otherwise stated (look for LICENSE files in directories or
$SP/charset_normalizer-3.4.7.dist-info/licenses/LICENSE | MIT License
$SP/click-8.3.3.dist-info/licenses/LICENSE.txt | Copyright 2014 Pallets
$SP/colorama-0.4.6.dist-info/licenses/LICENSE.txt | Copyright (c) 2010 Jonathan Hartley
$SP/coloredlogs-15.0.1.dist-info/LICENSE.txt | Copyright (c) 2020 Peter Odding
$SP/colorlog-6.10.1.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/croniter-6.2.2.dist-info/licenses/LICENSE | Copyright (C) 2010-2012 Matsumoto Taichi
$SP/cryptography-50.0.0.dist-info/licenses/LICENSE | This software is made available under the terms of *either* of the licenses
$SP/cryptography-50.0.0.dist-info/licenses/LICENSE.APACHE | Apache License
$SP/cryptography-50.0.0.dist-info/licenses/LICENSE.BSD | Copyright (c) Individual contributors.
$SP/ddtrace-4.11.0.dist-info/licenses/LICENSE | SPDX Apache-2.0 OR BSD-3-Clause`
$SP/ddtrace-4.11.0.dist-info/licenses/LICENSE.Apache | Apache License
$SP/ddtrace-4.11.0.dist-info/licenses/LICENSE.BSD3 | Copyright (c) 2016, Datadog <info@datadoghq.com>
$SP/ddtrace-4.11.0.dist-info/licenses/NOTICE | Datadog dd-trace-py
$SP/deprecated-1.3.1.dist-info/licenses/LICENSE.rst | The MIT License (MIT)
$SP/detect_secrets-1.5.0.dist-info/LICENSE | Apache License
$SP/distro-1.9.0.dist-info/LICENSE | Apache License
$SP/dnspython-2.8.0.dist-info/licenses/LICENSE | ISC License
$SP/docstring_parser-0.18.0.dist-info/licenses/LICENSE.md | The MIT License (MIT)
$SP/email_validator-2.3.0.dist-info/licenses/LICENSE | This is free and unencumbered software released into the public
$SP/envier-0.6.1.dist-info/licenses/LICENSE | MIT License
$SP/expression-5.6.0.dist-info/LICENSE | MIT License
$SP/fastapi-0.136.3.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/fastapi_sso-0.19.0.dist-info/licenses/LICENSE.md | # MIT License
$SP/fastuuid-0.14.0.dist-info/licenses/LICENSE | Copyright (c) 2019, Omer Katz
$SP/filelock-3.29.0.dist-info/licenses/LICENSE | MIT License
$SP/frozenlist-1.8.0.dist-info/licenses/LICENSE | Apache License
$SP/fsspec-2026.4.0.dist-info/licenses/LICENSE | BSD 3-Clause License
$SP/google_api_core-2.30.3.dist-info/licenses/LICENSE | Apache License
$SP/google_auth-2.52.0.dist-info/licenses/LICENSE | Apache License
$SP/google_cloud_aiplatform-1.133.0.dist-info/licenses/LICENSE | Apache License
$SP/google_cloud_bigquery-3.30.0.dist-info/LICENSE | Apache License
$SP/google_cloud_core-2.6.0.dist-info/licenses/LICENSE | Apache License
$SP/google_cloud_iam-2.19.1.dist-info/licenses/LICENSE | Apache License
$SP/google_cloud_kms-2.24.2.dist-info/LICENSE | Apache License
$SP/google_cloud_resource_manager-1.17.0.dist-info/licenses/LICENSE | Apache License
$SP/google_cloud_storage-3.10.1.dist-info/licenses/LICENSE | Apache License
$SP/google_crc32c-1.8.0.dist-info/licenses/LICENSE | Apache License
$SP/google_genai-1.37.0.dist-info/licenses/LICENSE | Apache License
$SP/google_resumable_media-2.9.0.dist-info/licenses/LICENSE | Apache License
$SP/googleapis_common_protos-1.75.0.dist-info/licenses/LICENSE | Apache License
$SP/granian-2.7.4.dist-info/licenses/LICENSE | Copyright 2021 Giovanni Barillari
$SP/grpc_google_iam_v1-0.14.4.dist-info/licenses/LICENSE | Apache License
$SP/grpcio-1.78.0.dist-info/licenses/LICENSE | Apache License
$SP/grpcio_status-1.71.2.dist-info/LICENSE | Apache License
$SP/gunicorn-23.0.0.dist-info/LICENSE | 2009-2024 (c) Benoît Chesneau <benoitc@gunicorn.org>
$SP/h11-0.16.0.dist-info/licenses/LICENSE.txt | The MIT License (MIT)
$SP/hf_xet-1.5.0.dist-info/licenses/LICENSE | Apache License
$SP/hiredis-3.4.0.dist-info/licenses/LICENSE | MIT License
$SP/httpcore-1.0.9.dist-info/licenses/LICENSE.md | Copyright © 2020, [Encode OSS Ltd](https://www.encode.io/).
$SP/httpx-0.28.1.dist-info/licenses/LICENSE.md | Copyright © 2019, [Encode OSS Ltd](https://www.encode.io/).
$SP/httpx_sse-0.4.3.dist-info/licenses/LICENSE | MIT License
$SP/huggingface_hub-1.14.0.dist-info/licenses/LICENSE | Apache License
$SP/humanfriendly-10.0.dist-info/LICENSE.txt | Copyright (c) 2021 Peter Odding
$SP/idna-3.15.dist-info/licenses/LICENSE.md | BSD 3-Clause License
$SP/ijson-3.5.1.dist-info/licenses/LICENSE.txt | ijson
$SP/importlib_metadata-8.5.0.dist-info/LICENSE | Apache License
$SP/inquirerpy-0.3.4.dist-info/LICENSE | MIT License
$SP/isodate-0.7.2.dist-info/LICENSE | Copyright (c) 2021, Hugo van Kemenade and contributors
$SP/jinja2-3.1.6.dist-info/licenses/LICENSE.txt | Copyright 2007 Pallets
$SP/jiter-0.14.0.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/jmespath-1.1.0.dist-info/LICENSE | MIT License
$SP/json_rpc-1.15.0.dist-info/LICENSE.txt | The MIT License (MIT)
$SP/jsonschema-4.26.0.dist-info/licenses/COPYING | Copyright (c) 2013 Julian Berman
$SP/jsonschema_specifications-2025.9.1.dist-info/licenses/COPYING | Copyright (c) 2022 Julian Berman
$SP/langfuse-2.59.7.dist-info/LICENSE | MIT License
$SP/litellm-1.101.0.dist-info/licenses/LICENSE | Portions of this software are licensed as follows:
$SP/litellm_enterprise-0.1.65.dist-info/licenses/LICENSE.md | The BerriAI Enterprise license (the "Enterprise License")
$SP/litellm_proxy_extras-0.4.94.dist-info/licenses/LICENSE | Portions of this software are licensed as follows:
$SP/llm_sandbox-0.3.39.dist-info/licenses/LICENSE | MIT License
$SP/lxml-6.1.1.dist-info/licenses/LICENSE.txt | BSD 3-Clause License
$SP/mangum-0.17.0.dist-info/LICENSE | MIT License
$SP/markdown_it_py-4.2.0.dist-info/licenses/LICENSE | MIT License
$SP/markdown_it_py-4.2.0.dist-info/licenses/LICENSE.markdown-it | Copyright (c) 2014 Vitaly Puzrin, Alex Kocharin.
$SP/markupsafe-3.0.3.dist-info/licenses/LICENSE.txt | Copyright 2010 Pallets
$SP/mcp-1.28.1.dist-info/licenses/LICENSE | MIT License
$SP/mdurl-0.1.2.dist-info/LICENSE | Copyright (c) 2015 Vitaly Puzrin, Alex Kocharin.
$SP/ml_dtypes-0.4.1.dist-info/LICENSE | Apache License
$SP/ml_dtypes-0.4.1.dist-info/LICENSE.eigen | Mozilla Public License Version 2.0
$SP/msal-1.37.0.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/msal_extensions-1.3.1.dist-info/LICENSE | MIT License
$SP/multidict-6.7.1.dist-info/licenses/LICENSE | Copyright 2016 Andrew Svetlov and aio-libs contributors
$SP/nodeenv-1.10.0.dist-info/licenses/LICENSE | Copyright (c) 2011, Eugene Kalinin.
$SP/numpy-2.4.4.dist-info/licenses/LICENSE.txt | Copyright (c) 2005-2025, NumPy Developers.
$SP/numpy-2.4.4.dist-info/licenses/numpy/_core/include/numpy/libdivide/LICENSE.txt | zlib License
$SP/numpy-2.4.4.dist-info/licenses/numpy/_core/src/common/pythoncapi-compat/COPYING | BSD Zero Clause License
$SP/numpy-2.4.4.dist-info/licenses/numpy/_core/src/highway/LICENSE | This project is primarily dual-licensed under your choice of either the Apache
$SP/numpy-2.4.4.dist-info/licenses/numpy/_core/src/npysort/x86-simd-sort/LICENSE.md | BSD 3-Clause License
$SP/numpy-2.4.4.dist-info/licenses/numpy/_core/src/umath/svml/LICENSE | Copyright (c) 2005-2021, NumPy Developers.
$SP/numpy-2.4.4.dist-info/licenses/numpy/fft/pocketfft/LICENSE.md | Copyright (C) 2010-2018 Max-Planck-Society
$SP/numpy-2.4.4.dist-info/licenses/numpy/linalg/lapack_lite/LICENSE.txt | Copyright (c) 1992-2013 The University of Tennessee and The University
$SP/numpy-2.4.4.dist-info/licenses/numpy/ma/LICENSE | * Copyright (c) 2006, University of Georgia and Pierre G.F. Gerard-Marchant
$SP/numpy-2.4.4.dist-info/licenses/numpy/random/LICENSE.md | **This software is dual-licensed under the The University of Illinois/NCSA
$SP/numpy-2.4.4.dist-info/licenses/numpy/random/src/distributions/LICENSE.md | ## NumPy
$SP/numpy-2.4.4.dist-info/licenses/numpy/random/src/mt19937/LICENSE.md | # MT19937
$SP/numpy-2.4.4.dist-info/licenses/numpy/random/src/pcg64/LICENSE.md | # PCG64
$SP/numpy-2.4.4.dist-info/licenses/numpy/random/src/philox/LICENSE.md | # PHILOX
$SP/numpy-2.4.4.dist-info/licenses/numpy/random/src/sfc64/LICENSE.md | # SFC64
$SP/numpy-2.4.4.dist-info/licenses/numpy/random/src/splitmix64/LICENSE.md | # SPLITMIX64
$SP/numpy/_core/include/numpy/random/LICENSE.txt | zlib License
$SP/numpy/ma/LICENSE | * Copyright (c) 2006, University of Georgia and Pierre G.F. Gerard-Marchant
$SP/numpy/random/LICENSE.md | **This software is dual-licensed under the The University of Illinois/NCSA
$SP/oauthlib-3.3.1.dist-info/licenses/LICENSE | Copyright (c) The OAuthlib Community
$SP/openai-2.33.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_api-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_exporter_otlp-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_exporter_otlp_proto_common-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_exporter_otlp_proto_grpc-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_exporter_otlp_proto_http-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_instrumentation-0.49b0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_instrumentation_asgi-0.49b0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_instrumentation_fastapi-0.49b0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_proto-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_sdk-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/opentelemetry_semantic_conventions-0.49b0.dist-info/licenses/LICENSE | Apache License
$SP/orjson-3.11.6.dist-info/licenses/LICENSE-APACHE | Apache License
$SP/orjson-3.11.6.dist-info/licenses/LICENSE-MIT | Permission is hereby granted, free of charge, to any
$SP/orjson-3.11.6.dist-info/licenses/LICENSE-MPL-2.0 | Mozilla Public License Version 2.0
$SP/packaging-26.2.dist-info/licenses/LICENSE | This software is made available under the terms of *either* of the licenses
$SP/packaging-26.2.dist-info/licenses/LICENSE.APACHE | Apache License
$SP/packaging-26.2.dist-info/licenses/LICENSE.BSD | Copyright (c) Donald Stufft and individual contributors.
$SP/pfzy-0.3.4.dist-info/LICENSE | MIT License
$SP/polars-1.38.1.dist-info/licenses/LICENSE | Copyright (c) 2025 Ritchie Vink
$SP/polars_runtime_32-1.38.1.dist-info/licenses/LICENSE | Copyright (c) 2025 Ritchie Vink
$SP/prisma-0.11.0.dist-info/LICENSE | Apache License
$SP/prometheus_client-0.20.0.dist-info/LICENSE | Apache License
$SP/prometheus_client-0.20.0.dist-info/NOTICE | Prometheus instrumentation library for Python applications
$SP/prompt_toolkit-3.0.52.dist-info/licenses/LICENSE | Copyright (c) 2014, Jonathan Slenders
$SP/propcache-0.5.2.dist-info/licenses/LICENSE | Apache License
$SP/propcache-0.5.2.dist-info/licenses/NOTICE | Copyright 2016-2021, Andrew Svetlov and aio-libs team
$SP/proto_plus-1.28.0.dist-info/licenses/LICENSE | Apache License
$SP/protobuf-5.29.6.dist-info/LICENSE | Copyright 2008 Google Inc.  All rights reserved.
$SP/psycopg-3.3.3.dist-info/licenses/LICENSE.txt | GNU LESSER GENERAL PUBLIC LICENSE
$SP/psycopg_binary-3.3.3.dist-info/licenses/LICENSE.txt | GNU LESSER GENERAL PUBLIC LICENSE
$SP/pyasn1-0.6.4.dist-info/licenses/LICENSE.rst | Copyright (c) 2005-2020, Ilya Etingof <etingof@gmail.com>
$SP/pyasn1_modules-0.4.2.dist-info/licenses/LICENSE.txt | Copyright (c) 2005-2020, Ilya Etingof <etingof@gmail.com>
$SP/pycparser-3.0.dist-info/licenses/LICENSE | pycparser -- A C parser in Python
$SP/pydantic-2.13.4.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/pydantic_core-2.46.4.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/pydantic_settings-2.14.2.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/pygments-2.20.0.dist-info/licenses/LICENSE | Copyright (c) 2006-2022 by the respective authors (see AUTHORS file).
$SP/pyjwt-2.13.0.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/pynacl-1.6.2.dist-info/licenses/LICENSE | Apache License
$SP/pynacl-1.6.2.dist-info/licenses/licenses/LICENSE.libsodium.txt | /*
$SP/pypdf-6.16.2.dist-info/licenses/LICENSE | Copyright (c) 2006-2008, Mathieu Fenniak
$SP/pyroscope_io-0.8.16.dist-info/licenses/LICENSE | Apache License
$SP/python3_saml-1.16.0.dist-info/LICENSE | Copyright (c) 2010-2022 OneLogin, Inc.
$SP/python_dateutil-2.9.0.post0.dist-info/LICENSE | Copyright 2017- Paul Ganssle <paul@ganssle.io>
$SP/python_dotenv-1.2.2.dist-info/licenses/LICENSE | Copyright (c) 2014, Saurabh Kumar (python-dotenv), 2013, Ted Tieken (django-dotenv-rw), 2013, Jacob 
$SP/python_multipart-0.0.32.dist-info/licenses/LICENSE.txt | Apache License
$SP/python_ulid-3.1.0.dist-info/licenses/LICENSE | Copyright (c) 2017 Martin Domke
$SP/pyyaml-6.0.3.dist-info/licenses/LICENSE | Copyright (c) 2017-2021 Ingy döt Net
$SP/redis-5.3.1.dist-info/LICENSE | MIT License
$SP/redisvl-0.4.1.dist-info/LICENSE | MIT License
$SP/referencing-0.36.2.dist-info/licenses/COPYING | Copyright (c) 2022 Julian Berman
$SP/regex-2026.5.9.dist-info/licenses/LICENSE.txt | This work was derived from the 're' module of CPython 2.6 and CPython 3.1,
$SP/requests-2.34.0.dist-info/licenses/LICENSE | Apache License
$SP/requests-2.34.0.dist-info/licenses/NOTICE | Requests
$SP/requests_toolbelt-1.0.0.dist-info/LICENSE | Copyright 2014 Ian Cordasco, Cory Benfield
$SP/resend-2.23.0.dist-info/LICENSE.md | Copyright (c) 2022 Derich Pacheco
$SP/restrictedpython-8.5.dist-info/licenses/LICENSE.txt | Zope Public License (ZPL) Version 2.1
$SP/rich-13.9.4.dist-info/LICENSE | Copyright (c) 2020 Will McGugan
$SP/rpds_py-0.30.0.dist-info/licenses/LICENSE | Copyright (c) 2023 Julian Berman
$SP/rq-2.7.0.dist-info/licenses/LICENSE | Copyright 2012 Vincent Driessen. All rights reserved.
$SP/s3transfer-0.17.0.dist-info/LICENSE.txt | Apache License
$SP/s3transfer-0.17.0.dist-info/NOTICE.txt | s3transfer
$SP/semantic_router-0.1.15.dist-info/licenses/LICENSE | MIT License
$SP/sentry_sdk-2.21.0.dist-info/LICENSE | MIT License
$SP/shellingham-1.5.4.dist-info/LICENSE | Copyright (c) 2018, Tzu-ping Chung <uranusjr@gmail.com>
$SP/six-1.17.0.dist-info/LICENSE | Copyright (c) 2010-2024 Benjamin Peterson
$SP/smithy_aws_core-0.7.0.dist-info/licenses/NOTICE | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
$SP/smithy_aws_event_stream-0.3.0.dist-info/licenses/NOTICE | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
$SP/smithy_core-0.6.0.dist-info/licenses/NOTICE | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
$SP/smithy_http-0.4.2.dist-info/licenses/NOTICE | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
$SP/smithy_json-0.2.3.dist-info/licenses/NOTICE | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
$SP/sniffio-1.3.1.dist-info/LICENSE | This software is made available under the terms of *either* of the
$SP/sniffio-1.3.1.dist-info/LICENSE.APACHE2 | Apache License
$SP/sniffio-1.3.1.dist-info/LICENSE.MIT | The MIT License (MIT)
$SP/soundfile-0.12.1.dist-info/LICENSE | Copyright (c) 2013, Bastian Bechtold
$SP/sse_starlette-3.4.4.dist-info/licenses/LICENSE | Copyright © 2020, [sysid](https://sysid.github.io/).
$SP/starlette-1.3.1.dist-info/licenses/LICENSE.md | Copyright © 2018, [Encode OSS Ltd](https://www.encode.io/).
$SP/tabulate-0.9.0.dist-info/LICENSE | Copyright (c) 2011-2020 Sergey Astanin and contributors
$SP/tenacity-8.5.0.dist-info/LICENSE | Apache License
$SP/tiktoken-0.12.0.dist-info/licenses/LICENSE | MIT License
$SP/tomlkit-0.15.0.dist-info/licenses/LICENSE | Copyright (c) 2018 Sébastien Eustace
$SP/tornado-6.5.8.dist-info/licenses/LICENSE | Apache License
$SP/tqdm-4.67.3.dist-info/licenses/LICENCE | `tqdm` is a product of collaborative work.
$SP/typer-0.25.1.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/typing_extensions-4.15.0.dist-info/licenses/LICENSE | A. HISTORY OF THE SOFTWARE
$SP/typing_inspection-0.4.2.dist-info/licenses/LICENSE | MIT License
$SP/tzlocal-5.3.1.dist-info/LICENSE.txt | Copyright 2011-2017 Lennart Regebro
$SP/urllib3-2.7.0.dist-info/licenses/LICENSE.txt | MIT License
$SP/uvicorn-0.51.0.dist-info/licenses/LICENSE.md | Copyright © 2017-present, [Encode OSS Ltd](https://www.encode.io/).
$SP/uvloop-0.22.1.dist-info/licenses/LICENSE-APACHE | Copyright (C) 2016-present the uvloop authors and contributors.
$SP/uvloop-0.22.1.dist-info/licenses/LICENSE-MIT | The MIT License
$SP/wcwidth-0.7.0.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/websockets-15.0.1.dist-info/LICENSE | Copyright (c) Aymeric Augustin and contributors
$SP/wrapt-1.17.3.dist-info/licenses/LICENSE | Copyright (c) 2013-2023, Graham Dumpleton
$SP/xmlsec-1.3.17.dist-info/licenses/LICENSE | The MIT License (MIT)
$SP/yarl-1.23.0.dist-info/licenses/LICENSE | Apache License
$SP/yarl-1.23.0.dist-info/licenses/NOTICE | Copyright 2016-2021, Andrew Svetlov and aio-libs team
$SP/zipp-3.23.1.dist-info/licenses/LICENSE | MIT License
/app/enterprise/LICENSE.md | The BerriAI Enterprise license (the "Enterprise License")
/app/litellm-proxy-extras/LICENSE | Portions of this software are licensed as follows:
/opt/prisma/binaries/node_modules/@prisma/engines/LICENSE | Apache License
/opt/prisma/binaries/node_modules/prisma/LICENSE | Apache License
/usr/lib/python3.13/LICENSE.txt | A. HISTORY OF THE SOFTWARE
/usr/share/doc/mpdecimal/COPYRIGHT.txt | SOURCE CODE LICENSE
/usr/share/licenses/opus/LICENSE | Copyright 2001-2023 Xiph.Org, Skype Limited, Octasic,
```

### List 2: every installed Python distribution (193) with the licence its own metadata declares

Read from each `METADATA`: `License-Expression`, else `License`, else the `License ::` classifier. Several metadata files give a free-text or an informal name (`Apache 2.0`, `MIT License`) rather than an SPDX identifier; they are quoted as written. The two distributions with no licence file in the image (`opentelemetry-util-http`, `tokenizers`) declare Apache-2.0 and the Apache classifier; no file in the image gives the text, so that declaration is the only evidence.

```text
a2a-sdk 1.1.0 | Apache-2.0
aiofiles 24.1.0 | Apache-2.0
aiohappyeyeballs 2.6.1 | PSF-2.0
aiohttp 3.14.3 | Apache-2.0 AND MIT
aiosignal 1.4.0 | Apache 2.0
annotated-doc 0.0.4 | MIT
annotated-types 0.7.0 | MIT License
anthropic 0.84.0 | MIT
anyio 4.13.0 | MIT
APScheduler 3.11.2 | MIT
asgiref 3.11.1 | BSD-3-Clause
attrs 26.1.0 | MIT
aurelio-sdk 0.0.19 | none declared; licence file: MIT License
aws-sdk-signers 0.3.0 | Apache License 2.0
aws_sdk_bedrock_runtime 0.7.0 | Apache-2.0
awscrt 0.32.2 | Apache-2.0
azure-ai-contentsafety 1.0.0 | MIT License
azure-core 1.41.0 | MIT
azure-identity 1.25.2 | MIT
azure-keyvault-secrets 4.10.0 | MIT License
azure-storage-blob 12.28.0 | MIT License
azure-storage-file-datalake 12.20.0 | MIT License
backoff 2.2.1 | MIT
boto3 1.43.1 | Apache-2.0
botocore 1.43.6 | Apache-2.0
bytecode 0.17.0 | The MIT License (MIT)
certifi 2026.4.22 | MPL-2.0
cffi 2.0.0 | MIT
charset-normalizer 3.4.7 | MIT
click 8.3.3 | BSD-3-Clause
colorama 0.4.6 | BSD License
coloredlogs 15.0.1 | MIT
colorlog 6.10.1 | MIT License
croniter 6.2.2 | MIT
cryptography 50.0.0 | Apache-2.0 OR BSD-3-Clause
ddtrace 4.11.0 | LICENSE.BSD3
Deprecated 1.3.1 | MIT
detect-secrets 1.5.0 | UNKNOWN in the licence field; classifier Apache Software License; licence file: Apache License
distro 1.9.0 | Apache License, Version 2.0
dnspython 2.8.0 | ISC
docstring_parser 0.18.0 | MIT
email-validator 2.3.0 | Unlicense
envier 0.6.1 | MIT License
Expression 5.6.0 | MIT
fastapi 0.136.3 | MIT
fastapi-sso 0.19.0 | MIT
fastuuid 0.14.0 | BSD License
filelock 3.29.0 | MIT
frozenlist 1.8.0 | Apache-2.0
fsspec 2026.4.0 | BSD-3-Clause
google-api-core 2.30.3 | Apache 2.0
google-auth 2.52.0 | Apache 2.0
google-cloud-aiplatform 1.133.0 | Apache 2.0
google-cloud-bigquery 3.30.0 | Apache 2.0
google-cloud-core 2.6.0 | Apache 2.0
google-cloud-iam 2.19.1 | Apache 2.0
google-cloud-kms 2.24.2 | Apache 2.0
google-cloud-resource-manager 1.17.0 | Apache 2.0
google-cloud-storage 3.10.1 | Apache 2.0
google-crc32c 1.8.0 | none declared; licence file: Apache License
google-genai 1.37.0 | Apache-2.0
google-resumable-media 2.9.0 | Apache 2.0
googleapis-common-protos 1.75.0 | Apache 2.0
granian 2.7.4 | BSD-3-Clause
grpc-google-iam-v1 0.14.4 | Apache 2.0
grpcio 1.78.0 | Apache-2.0
grpcio-status 1.71.2 | Apache License 2.0
gunicorn 23.0.0 | MIT
h11 0.16.0 | MIT
hf-xet 1.5.0 | Apache-2.0
hiredis 3.4.0 | MIT
httpcore 1.0.9 | BSD-3-Clause
httpx 0.28.1 | BSD-3-Clause
httpx-sse 0.4.3 | MIT
huggingface_hub 1.14.0 | Apache-2.0
humanfriendly 10.0 | MIT
idna 3.15 | BSD-3-Clause
ijson 3.5.1 | BSD-3-Clause AND ISC
importlib_metadata 8.5.0 | Apache Software License
inquirerpy 0.3.4 | MIT
isodate 0.7.2 | Copyright (c) 2021, Hugo van Kemenade and contributors
Jinja2 3.1.6 | BSD License
jiter 0.14.0 | MIT
jmespath 1.1.0 | MIT
json-rpc 1.15.0 | MIT
jsonschema 4.26.0 | MIT
jsonschema-specifications 2025.9.1 | MIT
langfuse 2.59.7 | MIT
litellm 1.101.0 | MIT
litellm-enterprise 0.1.65 | LicenseRef-Proprietary (COMMERCIAL: the BerriAI Enterprise licence)
litellm-proxy-extras 0.4.94 | MIT
llm-sandbox 0.3.39 | none declared; licence file: MIT License
lxml 6.1.1 | BSD-3-Clause
mangum 0.17.0 | MIT
markdown-it-py 4.2.0 | MIT License
MarkupSafe 3.0.3 | BSD-3-Clause
mcp 1.28.1 | MIT
mdurl 0.1.2 | MIT License
ml-dtypes 0.4.1 | Apache License
msal 1.37.0 | MIT
msal-extensions 1.3.1 | MIT License
multidict 6.7.1 | Apache License 2.0
nodeenv 1.10.0 | BSD
numpy 2.4.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0
oauthlib 3.3.1 | BSD-3-Clause
openai 2.33.0 | Apache-2.0
opentelemetry-api 1.28.0 | Apache-2.0
opentelemetry-exporter-otlp 1.28.0 | Apache-2.0
opentelemetry-exporter-otlp-proto-common 1.28.0 | Apache-2.0
opentelemetry-exporter-otlp-proto-grpc 1.28.0 | Apache-2.0
opentelemetry-exporter-otlp-proto-http 1.28.0 | Apache-2.0
opentelemetry-instrumentation 0.49b0 | Apache-2.0
opentelemetry-instrumentation-asgi 0.49b0 | Apache-2.0
opentelemetry-instrumentation-fastapi 0.49b0 | Apache-2.0
opentelemetry-proto 1.28.0 | Apache-2.0
opentelemetry-sdk 1.28.0 | Apache-2.0
opentelemetry-semantic-conventions 0.49b0 | Apache-2.0
opentelemetry-util-http 0.49b0 | Apache-2.0; no licence file in the image
orjson 3.11.6 | MPL-2.0 AND (Apache-2.0 OR MIT)
packaging 26.2 | Apache-2.0 OR BSD-2-Clause
pfzy 0.3.4 | MIT
polars 1.38.1 | Copyright (c) 2025 Ritchie Vink
polars-runtime-32 1.38.1 | MIT License
prisma 0.11.0 | APACHE
prometheus_client 0.20.0 | Apache Software License 2.0
prompt_toolkit 3.0.52 | BSD License
propcache 0.5.2 | Apache-2.0
proto-plus 1.28.0 | Apache 2.0
protobuf 5.29.6 | 3-Clause BSD License
psycopg 3.3.3 | LGPL-3.0-only
psycopg-binary 3.3.3 | LGPL-3.0-only
pyasn1 0.6.4 | BSD-2-Clause
pyasn1_modules 0.4.2 | BSD
pycparser 3.0 | BSD-3-Clause
pydantic 2.13.4 | MIT
pydantic-settings 2.14.2 | MIT
pydantic_core 2.46.4 | MIT
Pygments 2.20.0 | BSD-2-Clause
PyJWT 2.13.0 | MIT
PyNaCl 1.6.2 | Apache-2.0
pypdf 6.16.2 | BSD-3-Clause
pyroscope-io 0.8.16 | Apache 2.0
python-dateutil 2.9.0.post0 | Dual License
python-dotenv 1.2.2 | BSD-3-Clause
python-multipart 0.0.32 | Apache-2.0
python-ulid 3.1.0 | MIT
python3-saml 1.16.0 | MIT
PyYAML 6.0.3 | MIT
redis 5.3.1 | MIT
redisvl 0.4.1 | MIT
referencing 0.36.2 | MIT
regex 2026.5.9 | Apache-2.0 AND CNRI-Python
requests 2.34.0 | Apache-2.0
requests-toolbelt 1.0.0 | Apache 2.0
resend 2.23.0 | MIT License
RestrictedPython 8.5 | ZPL-2.1
rich 13.9.4 | MIT
rpds-py 0.30.0 | MIT
rq 2.7.0 | BSD-2-Clause
s3transfer 0.17.0 | Apache License 2.0
semantic-router 0.1.15 | MIT
sentry-sdk 2.21.0 | MIT
shellingham 1.5.4 | ISC License
six 1.17.0 | MIT
smithy-aws-core 0.7.0 | Apache License 2.0
smithy-aws-event-stream 0.3.0 | Apache License 2.0
smithy-core 0.6.0 | Apache License 2.0
smithy-http 0.4.2 | Apache License 2.0
smithy-json 0.2.3 | Apache License 2.0
sniffio 1.3.1 | MIT OR Apache-2.0
soundfile 0.12.1 | BSD 3-Clause License
sse-starlette 3.4.4 | BSD-3-Clause
starlette 1.3.1 | BSD-3-Clause
tabulate 0.9.0 | MIT
tenacity 8.5.0 | Apache 2.0
tiktoken 0.12.0 | MIT License
tokenizers 0.23.1 | Apache Software License; no licence file in the image
tomlkit 0.15.0 | MIT
tornado 6.5.8 | Apache-2.0
tqdm 4.67.3 | MPL-2.0 AND MIT
typer 0.25.1 | MIT
typing-inspection 0.4.2 | MIT
typing_extensions 4.15.0 | PSF-2.0
tzlocal 5.3.1 | MIT
urllib3 2.7.0 | MIT
uvicorn 0.51.0 | BSD-3-Clause
uvloop 0.22.1 | MIT License
wcwidth 0.7.0 | MIT
websockets 15.0.1 | BSD-3-Clause
wrapt 1.17.3 | BSD
xmlsec 1.3.17 | MIT
yarl 1.23.0 | Apache-2.0
zipp 3.23.1 | MIT
```

### List 3: every operating-system package of the Wolfi base (48) with the licence its database record declares

Read from `/lib/apk/db/installed` (the `L:` line of each record). The licence texts of these packages sit in a file for only two of them (`opus` and `mpdecimal`, list 1); the others carry their declaration in the database alone.

```text
alsa-lib 1.2.16.1-r2 | LGPL-2.1-or-later
apk-tools 2.14.10-r13 | GPL-2.0-only
bash 5.3-r13 | GPL-3.0-or-later
busybox 1.38.0-r2 | GPL-2.0-only
c-ares 1.34.8-r2 | MIT
ca-certificates-bundle 20260611-r0 | MPL-2.0 AND MIT
gdbm 1.26-r6 | GPL-3.0-or-later
glibc-2.44 2.44-r1 | LGPL-2.1-or-later
glibc-2.44-locale-posix 2.44-r1 | LGPL-2.1-or-later
icu78-data-full 78.3-r3 | MIT
ld-linux-2.44 2.44-r1 | LGPL-2.1-or-later
libbrotlicommon1 1.2.0-r5 | MIT
libbrotlidec1 1.2.0-r5 | MIT
libbrotlienc1 1.2.0-r5 | MIT
libbz2-1 1.0.8-r24 | MPL-2.0 AND MIT
libcrypt1-2.44 2.44-r1 | LGPL-2.1-or-later
libcrypto3 3.6.4-r0 | Apache-2.0
libexpat1 2.8.4-r0 | MIT
libffi 3.8.0-r1 | MIT
libflac 1.5.0-r1 | BSD-3-Clause AND GPL-2.0-or-later
libgcc 16.2.0-r1 | GPL-3.0-or-later WITH GCC-exception-3.1
libicu78 78.3-r3 | MIT
libnghttp2-14 1.70.0-r3 | MIT
libogg-libs 1.3.6-r9 | BSD-3-Clause
libsndfile 1.2.2-r5 | LGPL-2.1-or-later
libssl3 3.6.4-r0 | Apache-2.0
libstdc++ 16.2.0-r1 | GPL-3.0-or-later WITH GCC-exception-3.1
libuuid 2.42.3-r3 | GPL-3.0-or-later AND GPL-2.0-or-later AND GPL-2.0-only AND GPL-1.0-only AND LGPL-2.1-or-later AND BSD-1-Clause AND BSD-2-Clause AND BSD-3-Clause AND BSD-4-Clause-UC AND MIT AND CC-PDDC
libuv 1.52.1-r2 | MIT AND ISC
libvorbis 1.3.7-r11 | BSD-3-Clause
libxcrypt 4.5.2-r4 | GPL-2.0-or-later AND LGPL-2.1-or-later
mpdecimal 4.0.1-r4 | BSD-2-Clause
ncurses 6.6.20260912-r0 | MIT
ncurses-terminfo-base 6.6.20260912-r0 | MIT
nodejs-26 26.8.2-r1 | MIT
openssl 3.6.4-r4 | Apache-2.0
opus 1.6.1-r5 | BSD-3-Clause
py3-pip-wheel 26.2.1-r1 | MIT
python-3.13 3.13.15_git20260912-r0 | PSF-2.0
python-3.13-base 3.13.15_git20260912-r0 | PSF-2.0
readline 8.3-r3 | GPL-3.0-or-later
sqlite-libs 3.53.4-r2 | blessing
tzdata 2026d-r0 | CC-PDDC
wolfi-base 1-r7 | MIT
wolfi-baselayout 20230201-r29 | MIT
wolfi-keys 1-r13 | MIT
xz 5.8.4-r0 | GPL-3.0-or-later
zlib 1.3.2-r5 | MPL-2.0 AND MIT
```

## What I ran, exactly

Everything in `/tmp` and Docker, named `pl13-scout-<id>`; nothing in the repository or the home folder; the owner's `osprey-local-lite-*` containers, ports, volumes and network were not touched, and `make dev-up`, `ospreyflow start` and `docker compose` were not run. The master and salt keys of each gateway were made at run time (`openssl rand`), held in the shell and in that container's environment only, and the containers were removed. No hosted provider or real model was called: the stand-in upstreams answered.

1. `docker create` and `docker export` of the pinned image into a scratch folder; `docker rm`.
2. `docker build` of two scratch images from it (one `RUN rm -rf` each), removed after.
3. Per variant: one network, one `postgres:16.4`, one stand-in upstream (the pinned image's own Python), one gateway with the rendered config, port `127.0.0.1:` ephemeral; the 24-call script; the container logs read; all removed.
4. The repository's `test_model_gateway_live.py` through pytest against (a) and (c).
5. `git archive` of `lane/slice-AD1a` into a scratch folder and pytest there; pytest on this worktree for the main-side files.
6. `uv venv` and `uv pip install` into a scratch environment; PyPI's JSON, sdist and one wheel downloaded and hash-checked.
7. Row 9's lists (this round): `docker create` (no start) and `docker export` of the pinned image by digest into a scratch folder, `docker rm`; a Python script kept outside that folder, run with `-I`, walked the export for licence-named files and read every `METADATA` and the Wolfi package database. No container ran, no port was opened, no network was used; the scratch folder is deleted afterwards.

## How this file was made

**Correction after the verifier's finding.** The verifier found that the first draft's `signatures.py` diff (one line, `litellm` added to
`OPTIONAL_OWNED_SERVICES`) would have refused every older lock, because those name the publisher's gateway under the same
service name `litellm`; its comment ("a lock from before names the publisher's image, a third party's, and none of it is checked") was wrong. Confirmed by reading
`render.py` 1844-1855, `owned_references`, `bundle.py` 320 and `update.py` 368-369, and by running the one-line change in
memory against an older lock (refused, red) and the replacement (verifies, green). The patch now checks the repository as well
as the name, in all three places that used the name alone. Rows 1 to 5, 7 and 8 are unchanged and stand on the earlier
sessions' runs.

**Correction after the second verifier's finding (row 9).** Row 9 said "Full list by path below" and gave seven rows and a lump of "230-odd"; it also counted "110" distributions and called three packages that declare no licence "not commercial" without saying what licence file they carry. This round re-exported the pinned image's filesystem (one container created, never started, removed), walked it again and replaced the lump with the three complete lists at the end of the file's licence section: 242 licence-named files, 193 distributions, 48 operating-system packages. The three undeclared packages each carry a licence file (MIT, Apache, MIT), now read and named; the two with no licence file are said so. The earlier counts (241 files, 110 distributions) were wrong and are corrected in row 9.

An earlier session of this slice drafted it in scratch and stopped before committing. This session re-read, from the
pinned image's exported filesystem, the top-level `LICENSE`, the enterprise `LICENSE.md` (and checked the two copies are
identical), the import lines in `proxy_server.py` and `proxy/hooks/__init__.py`, the `litellm` and `litellm-enterprise`
metadata, and the 211 files under `/app/enterprise`; read the earlier session's scratch logs for the live usage test (passed
against variants (a) and (c)); and re-ran `git apply --check` on the patch below against main (c71c727). It corrected one
quotation (the enterprise licence's last sentence). The three-gateway route runs in row 1 were **not re-run** in this
session; they stand on the earlier session's scratch logs, which were read.

## The protected-file diffs (two patches for the owner to apply; each passes `git apply --check` against main on its own, c71c727, whose five files are identical on aad2df3)

**Patch 1 (signature check) may be applied at any time**, alone: it is safe before or after the build and the render switch (row 6). **Patch 2 (release matrix and Core Makefile) must wait until the build's `deploy/litellm/Dockerfile` is on main**: applied earlier it fails `make ci` (a `docker build` of a missing Dockerfile) and the next release. The two patches touch different files, so either leaves the other applicable.

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
