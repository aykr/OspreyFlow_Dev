# PL11: what a default install downloads or ships, and its licence as the repository states it (read-only scout, 21 November 2026)

For the owner's decision before any PL11 builder starts. Read, not run; nothing was fetched from the internet, so every licence is **what the repository itself says** and "not stated" is an answer. "Default" means `osprey.yaml` as shipped (profile local-lite, search opensearch, Keycloak, Superset on) plus the images and pulls the renderer writes unconditionally. Paths: CORE = `OspreyFlow_Core/`, BUILD = `OspreyFlow_Build/`. The scout read `cli/ospreyflow/` by search and not end to end; an install step it did not see is marked "not shown".

## The table

| # | Kind | Name, version or tag | What ships it, and when | Named at | Licence as stated, and where | Open source? |
|---|---|---|---|---|---|---|
| W1 | weight | qwen2.5:7b-instruct (manifest 845dbda0ea48), default extraction model | default; pulled at first start when absent (CORE/harness/render.py:893-896, model_downloads.py:4-7) | CORE/packages/schemas/deployment.py:249-250; render.py:189-190 | Apache-2.0: BUILD/spec/06_DECISIONS.md:10164 | **yes** (on the §7 allowlist, spec/00_ARCHITECTURE.md:925). Note: osprey.yaml:19-22 routes extraction to Gemini, yet the 7b stays the extraction model unless `models.extraction` is named (deployment.py:2368-2373) |
| W2 | weight | qwen2.5:14b-instruct (7cdf5a0187d5) | NOT default: only with `resources.gpu` nvidia (deployment.py:2370) | deployment.py:251 | Apache-2.0: spec/06_DECISIONS.md:10165 | yes |
| W3 | weight | qwen2.5:0.5b-instruct (a8b0c5157701), conformance and chat route | default; always in the pull script (render.py:166), routed at 471-474 | render.py:166 | **not stated** (searched spec/ and CORE) | **not stated** |
| W4 | weight | all-minilm:22m-l6-v2-fp16 (1b226e2802db), embeddings | default; pulled (render.py:167) | render.py:167, 480-483; deployment.py:254 | **not stated** | **not stated** |
| W5 | weight | moondream:1.8b-v2-q4_K_M (c865c80afc38), vision | default; pulled (render.py:168), not waited on (211-218) | render.py:168; deployment.py:253 | **not stated** | **not stated** |
| W6 | weight | Systran/faster-whisper-tiny.en (HF commit 0d3d19a3…), transcription | default container `whisper` (speaches image, render.py:679-682); when the weights are fetched is not stated | render.py:494-498; deployment.py:256; spec/06_DECISIONS.md:1061-1062 | weights **not stated**; the speaches server image is MIT (spec/06:1063-1064), which is the software, not the weights | **not stated** (weights) |
| W7 | weight | Stanza English models (tokenize, ner, pretrain conll17, charlm, mwt, resources.json) | default; downloaded when the `ner` image is built, so they ship in it (render.py:636) | CORE/services/ner/Dockerfile:30; models.sha256:1-7 | Stanza library Apache-2.0 (spec/04_VAULT_BACKEND.md:291; requirements.txt:4). **Model licence not stated** | **not stated** (library: yes) |
| W8 | weight | spaCy en_core_web_sm; dslim/bert-base-NER | NOT shown as default: ADR-108 adapters exist; the HF cache is "fetched once", timing not stated | spec/00_ARCHITECTURE.md:1001-1004 | MIT for both, as the repository states ("MIT, per its model card" for dslim) (spec/00:1002-1003) | yes, by the repository's own statement |
| M1 | map data | OpenStreetMap basemap, Great Britain: `osm-local-great-britain` (great-britain.pmtiles), the map default | **not shipped**: built on demand from the Geofabrik GB extract by planetiler (scripts/build_local_basemap.py:112); no default-install step that builds it was found (not shown) | osprey.yaml:33-34, 48-59 | ODbL, `redistributable: true`, `client_scope: open` (osprey.yaml:39-42, 51-54); spec/00:997-999 | open by the map registry's own `client_scope: open`; **ODbL is not on the §7 allowlist, which governs code**. Your call |
| M2 | map data | `osm-local` (file:///data/tiles/osm-local.pmtiles), second entry | named by the default config; the code that produces this file was not found | osprey.yaml:36-47 | ODbL, same as M1 (osprey.yaml:39-42) | as M1 |
| M3 | map data (auxiliary) | planetiler's lake centrelines, water polygons, Natural Earth | on demand, at basemap build, via `planetiler --download` | scripts/build_local_basemap.py:218-223 | **not stated** in the repository | **not stated** |
| F1 | font | Atkinson Hyperlegible Next 5.3.0 (@fontsource; 400, 600, 700) | default; bundled into the Glass build | workspace/package.json:20; fonts.ts:3-5; packages/design/fonts.json:4-9 | OFL-1.1: fonts.json:8 | **yes** (SIL-OFL-1.1 is on the allowlist, spec/00:925) |
| F2 | font | IBM Plex Mono 5.3.0 (@fontsource; 400, 600) | default; bundled | workspace/package.json:21; fonts.ts:6-7; fonts.json:11-16 | OFL-1.1: fonts.json:15 | yes |
| F3 | font | **GDS Transport** (faces bold, light) from govuk-frontend 6.6.0 | default **build**: `build` runs `sync_govuk_assets.mjs` unconditionally (workspace/package.json:8) and the files are in `public/assets/govuk/fonts` and in `dist/`; use is conditional on `appearance.govuk_identity` (fonts.json:23-24) | workspace/package.json:30; fonts.json:18-26 | "Restricted to services on GOV.UK domains; not OFL (spec/00_ARCHITECTURE.md, ADR-132)": fonts.json:22 | **NO** (restricted, free to use only on GOV.UK domains) |
| F4 | font | Noto Sans Regular, OpenMapTiles fonts v2.0 zip | NOT default: an operator runs `python -m scripts.fetch_basemap_glyphs`; no CLI call found; an empty folder is accepted (render.py:1054-1055) | scripts/fetch_basemap_glyphs.py:28-32 | SIL-OFL-1.1: fetch_basemap_glyphs.py:9-11; spec/00:995-996 | yes |
| B1 | base image | arcadedata/arcadedb:26.10.1 | default (graph store) | render.py:640 | **not stated** (spec/00:1157 names only the ArangoDB-to-ArcadeDB relicence) | **not stated** |
| B2 | base image | valkey/valkey:8.0 | default | render.py:645 | BSD-3: spec/04:287; spec/06:249 | yes |
| B3 | base image | chrislusf/seaweedfs:4.48 | default (object store) | render.py:646-647 | Apache-2.0: render.py:646; spec/04:298 | yes |
| B4 | base image | postgres:16.4 | default | render.py:1373, 1510 | "PostgreSQL Licence": spec/04:290 | yes by the OSI test (the name is from general knowledge, not the repository; **not on the §7 allowlist**) |
| B5 | base image | quay.io/keycloak/keycloak:26.0 | default | render.py:649 | Apache-2.0: spec/04:289 | yes |
| B6 | base image | caddy:2.11.4-alpine | default (front proxy) | harness/site.py:29; render.py:651 | Apache-2.0: spec/00:1026-1027 | yes |
| B7 | base image | ollama/ollama@sha256:5a5d014a… | default | render.py:653-655 | **not stated** | **not stated** |
| B8 | base image | ghcr.io/berriai/litellm@sha256:d295634e… | default | render.py:675-677 | "MIT, self-hostable" (spec/00:764); "MIT core" (spec/04:218) | yes (MIT core only) |
| B9 | base image | ghcr.io/speaches-ai/speaches@sha256:21e3df06… | default | render.py:679-681 | MIT: spec/06:1064 | yes |
| B10 | base image | opensearchproject/opensearch:2.17.1 | default | render.py:692 | Apache-2.0: spec/06:249 | yes |
| B11 | base image | apache/superset@sha256:16b50bbe… | default | CORE/deploy/superset/Dockerfile:11 | Apache-2.0: spec/00:1015 | yes |
| B12 | base image | **eclipse-temurin:21-jdk**@sha256:ebfbb18d…, the jlinked runtime in the `api` image | default build of `api` (services/api/Dockerfile:53; which runtime variant is chosen by `CONDUIT_JAVA` at :83, default not read) | services/api/Dockerfile:53, 73-75 | "GPL-2.0-only WITH Classpath-exception-2.0": Dockerfile:74; spec/00:947-953 | **NO** by §7; admitted only by a recorded exception for that runtime (spec/00:947-960), and "distributing the image distributes the runtime under GPL-2.0" (spec/00:953-954) |
| B13 | base image | python:3.12-slim (api, ingest, worker, report_sync, ner, harness); python:3.13-slim@sha256:e48f59… for laurium (default not verified) | default | services/api/Dockerfile:16,65,80; ingest:9,20; worker:7,18; report_sync:5,16; ner:3; harness/Dockerfile:43,121; laurium/Dockerfile:5 | **not stated** (OS and Python licences are stated nowhere in the repository) | **not stated** |
| B14 | base image | node:22-slim (workspace, pages, harness builders) | default | workspace/Dockerfile:18; pages/Dockerfile:18,34,44; harness/Dockerfile:90 | **not stated** | **not stated** |
| B15 | base image | nginx:1.30-alpine (workspace runtime) | default | workspace/Dockerfile:58 | **not stated** | **not stated** |
| B16 | base image | docker:29-cli | default (harness) | harness/Dockerfile:82 | **not stated** | **not stated** |

Not default and not in the table: `os-open-zoomstack` (OGL-UK-3.0, providers/os-open-zoomstack.yaml:36-40), `usgs-national-map`, the hosted Gemini model `gemini-3-flash-preview` (a hosted service, not a download), the qwen 14b (W2), the enterprise ClickHouse image (render.py:693-695). The `ner` image's CPU torch wheel (ner/Dockerfile:19; BSD-3-Clause per spec/00:1002-1003) is software, not a weight.

## (a) For your decision: not clearly open source

1. **GDS Transport (F3).** The repository: "Restricted to services on GOV.UK domains; not OFL" (fonts.json:22). **Its files are in the default build** (`apps/workspace/public/assets/govuk/fonts/`, and `dist/`). Restricted-but-free-to-use is not open source.
2. **Eclipse Temurin in the api image (B12).** GPL-2.0-only with the Classpath exception (Dockerfile:74), admitted by an existing recorded exception (spec/00:947-960).
3. **The OpenStreetMap basemap (M1, M2).** ODbL, which the map registry marks `client_scope: open`; ODbL is not on the §7 code allowlist.
4. **No licence stated for five weights:** qwen2.5:0.5b-instruct (W3), all-minilm (W4), moondream (W5), faster-whisper-tiny.en (W6), the Stanza models (W7). **These are the ones that are your decision; the repository cannot tell either of us.**
5. **No licence stated for these images:** arcadedb (B1), ollama (B7), the Python, Node, nginx and Docker CLI bases (B13 to B16). **No licence stated for the data:** planetiler's auxiliary sources (M3).
6. PostgreSQL's licence (B4) is named but is not on the §7 allowlist.

## (b) Pulled at run time, with a name known only at run time (what a register would have to pin)

- Planetiler's auxiliary sources (M3): downloaded by `planetiler --download`; the names live inside planetiler's jar. Pin: planetiler's version and jar SHA, and the source list with SHA-256s.
- Whisper weights (W6): the Hugging Face commit is in the ADR (spec/06:1061-1062) but not in `render.py`; how and when speaches fetches it is not in the repository. Pin: the revision and file SHA in the render or LiteLLM config, and the fetch step.
- dslim/bert-base-NER and en_core_web_sm (W8): fetched into the HF cache "once"; no pin in the files read. Pin: revision and SHA.
- Ollama models (W1 to W5) are named statically and pinned by manifest digest, verified after the pull (render.py:146-160); the tag can move upstream (ADR-020) and the script fails loudly when it does.

## (c) What the existing licence gate checks, and what it cannot see

The gate: `BUILD/tools/licence_check.py` and `BUILD/tools/licence_check.mjs` (what Makefile:93 runs), tests in `BUILD/tests/licence_check/`. **It checks:** the pip environment's declared package licences (licence_check.py:357-362, main at 418); root LICENSE and NOTICE (365-379); demo manifests' `data_licence` only (382-415); runtime labels in Dockerfiles, `org.ospreyflow.runtime.*.licence` (find_runtime_offenders, 319; services/api/Dockerfile:73-75); the npm packages' declared licences via license-checker (licence_check.mjs:118, 138); the `ner` image's own pip packages at build (services/ner/licence_gate.py). **It cannot see:** model weights (not packages); map data outside demo manifests; font files and their own restrictions (it reads package metadata, so the GDS restriction at fonts.json:22 is not a declared licence); base-image OS and runtime licences, except B12, which carries a label; the Stanza model files; the planetiler jar.

## (d) Where the gate would need to be wired (three places; the Makefile is protected, only named)

1. A new leg in `BUILD/tools/licence_check.py`, beside `find_data_licence_offenders` (line 382) and in `main()` (418), reading one register file listing each weight, map dataset, font and base image with its licence and where that licence is stated.
2. The `licence-check` target (BUILD/Makefile:91-95), to run that leg and its test under `tests/licence_check/`.
3. The image and render layer: the `FROM` lines in the Dockerfiles, the `ServiceImage` list in `harness/render.py:631-684`, the pull list at render.py:166-168 and the closed model lists at deployment.py:249-256. Each entry checked against the register; base images carrying a licence `LABEL` as the runtime ones do (licence_check.py:220-233).

## What I recommend, once you have decided

The register can only hold what the repository states. For the "not stated" rows someone must read the source (a model card, an image's licence file) and write it down with where it was read; that is a task for a builder with the internet, and **I have not done it from memory**. Until you decide the items in (a), PL11 builds the register, the gate and the Makefile diff with those rows **marked "undecided by the owner"** and the gate failing closed on them (a row with no licence and no owner decision fails), so nothing passes by being absent.
