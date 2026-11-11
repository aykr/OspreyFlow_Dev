# case-b · P12 part 1 · server log (11 November 2026)

The case-b lane on the test server, in `~/osprey-srv/case-b` on `lane/case-b-p12` (from main at 459ae1d4),
while the orchestrator's laptop is offline (about 07:15 to 11:00 UTC). P12 part 1: Laurium as a second
extraction engine, as its own Python 3.13 service (ADR-142 Amendment 8; `platform/BRIEF_P12.md`,
`platform/p12/LICENCE_CHECK.md`). Times are UTC.

## What I did

- Read rules 1–15, PROMPT_L, ADR-135 Amendments 4–5, ADR-142 Amendment 8, BRIEF_P12 and LICENCE_CHECK.
- Resolved Laurium's tree for Python 3.13 on manylinux_2_28 x86_64 with hashes
  (`uv pip compile --only-binary :all: --generate-hashes`): 126 packages, the licence check's 121 plus
  FastAPI, Starlette, Uvicorn and their own; `en-core-web-sm` 3.8.0 from Explosion's GitHub release,
  sha256 `1932429d…0fb85`. Read Laurium 0.6.0's source from its wheel (no code of it run to read it).
- **ADR-135 Amendment 6 written first** (f6f85fcf), then, each test red first: the service
  (`services/laurium/`: settings checked at start, schema mapping, the app, its image licence gate, Dockerfile,
  NOTICE); the adapter (`packages/adapters/extract_laurium/`); `ModelPort.extract`'s suite on both engines; the
  licence record; `tools/no_langchain_check.py`; the ci.yml and Makefile diffs (`P12_CI.diff`,
  `P12_MAKEFILE.diff`).
- **The image builds** (`docker build -t case-b-laurium:p12 services/laurium`, base `python:3.13-slim@sha256:
  e48f59cd…`): `pip install --require-hashes --only-binary :all:` and `pip check` pass, and the image's own licence
  gate passes all 126 packages, naming the three admitted by recorded evidence and no other.
- **Run through the gateway's stand-in, never a real gateway or model**: in Laurium's own 3.13 environment (built
  by hash by the new `make laurium-service`), the service's real code with Laurium 0.6.0, LangChain and the OpenAI
  client, every call over real HTTP to the stand-in served as `litellm`: at a5fa3c1b, 26 passed (14 of the
  service, 12 of the suite: 6 cases × 2 engines). In the Conduit's environment the suite's LiteLLM cases pass and
  the Laurium cases skip with their reason. (After the review round: 26 = 17 + 4 × 2 + 1, below.)
- **Red record** (`P12_RED_RECORD.md`, `plants_P12.py`): at a5fa3c1b, 45 offline plants and 9 in Laurium's
  environment, all red; after the review round 53 and 14. Tests found passing for another reason were fixed each
  round; a stale-bytecode fault in the plant runner found and fixed (friction row
  `2026-11-11-case-b-laurium-stale-bytecode.md`).

## Decisions taken (the owner may overrule each)

1. **No heartbeats from the server.** `lanes_heartbeat.sh` reports to the orchestrator's session, which is
   offline; this log stands in for them.
2. **The service awaits Laurium's chain, not `BatchExtractor.process_chunk`.** Read in Laurium 0.6.0's
   `decoder_models/extract.py`: `BatchExtractor` catches every failure of a row (a refused key, an unknown model,
   unparseable output) and returns that row with **every field `None`**. Through a DataFrame that is a silent empty
   finding for "the gateway refused" (rules 2 and 5). Options: `process_chunk` and treat an all-`None` row as a
   failure (loses the reason; a one-field schema with nothing found looks the same), or our own LangChain chain (no
   longer Laurium). Chose: build Laurium's `BatchExtractor` (its prompt, parser and chain) and await its documented
   `chain` for the one document. Planted red: "a gateway refusal answered as Laurium's row of Nones".
3. **Laurium's `create_llm` only on `openai`, the gateway's host fixed as `litellm`, not a setting.** Its other
   platforms each reach their own host, so the service offers no platform setting at all; a host that could be set
   could be set to anything. The compose and Helm renders name the gateway `litellm`. Also refused at start: the
   libraries' own host settings (OpenAI, Anthropic, Ollama, AWS endpoints, LangSmith's endpoint, proxies),
   LangSmith tracing on, any unknown `OSPREY_LAURIUM_*`; the words name the setting, never its value.
4. **No `ospreyflow[laurium]` extra and no `uv.lock` change.** Amendment 6 replaces Amendment 5 decision 1's extra
   (Laurium cannot install into 3.12), so the brief's "shared commit first" has nothing to carry. **Schema and
   dependency changes: none.** `packages/schemas` untouched; `pyproject.toml` gains only a mypy override
   (`laurium.*`, `langchain_core.*`, `openai.*`, installed only in Laurium's image), as the recognisers have.
5. **The gateway token travels with each call**, from the adapter to the service in `Authorization`, with the
   call's tag; the service keeps no key. *Amended by the orchestrator's ruling (review item 7, ADR decision 8):*
   never the master key. A hosted engine's own key, or for the deployment's own models and an unrouted call
   Laurium's own scoped key (`adapters/extract_laurium/keys.py`). So per-engine limits and usage apply to
   Laurium's calls as to Deep read's (planted red).
6. **Schema subset.** Every top-level property must be required (Laurium's model makes every field required); an
   object may not say `additionalProperties: true`; left unsaid, extras are allowed by the schema but refused in
   the answer (stricter). Laurium reports no span: spans are located in the text by `services/extract/
   candidates.py`, as for Deep read, and a finding the text does not contain is dropped there.
7. **The OpenAI client's own retries: off** (changed in the lane-reviewer's round, finding 3). Laurium's
   `create_llm` does not expose `max_retries`, so the service sets `max_retries=0` on Laurium's model's clients; a
   refused call is answered once.
8. **The real service tested in-process, not in its container.** `docker run` asks for approval in this
   unattended session (`docker build` does not), and I did not route around that. The service's tests import its
   app as the image does and reach it through `httpx.ASGITransport`; only the name `litellm` is pointed at
   127.0.0.1, for the test process alone. `uv run` was used to run pytest in Laurium's environment.
9. **Laurium's image is built from its own folder**; `.dockerignore` now leaves `services/laurium` out of the
   Conduit's build context, so no other image carries even its source.
10. **spaCy:** allowed in the Conduit's lock (ADR-108's optional `extraction` extra, which no image installs),
    refused in every image built without Laurium.
11. **The Ministry of Justice's notices**: a short entry in the product NOTICE, the full notices in the image's
    own `services/laurium/NOTICE`.
12. **"Proven on local-lite"**: *corrected (review item 1).* What was actually run is narrower than the
    brief's words. Laurium's service code was imported in-process in a Python 3.13 virtual environment on this
    server and reached through `httpx.ASGITransport`. Its model calls went over real HTTP on 127.0.0.1 to the
    in-process stand-in, served under the name `litellm`, and the stand-in answers a fixed string whatever the
    prompt says. Not the local-lite compose stack, not the built image, not the real LiteLLM, and no model. So
    nothing has shown that a real model's answer to Laurium's prompt parses. Brief's exit "proven on local-lite"
    is **not met**; the leased live run that would meet it is carried (below). Rendering the service into the
    local-lite compose stays with part 2, with the setting that chooses it.
13. **The scratch environment** I made to read Laurium's source (`OspreyFlow_Core/services/laurium/.venv`,
    untracked) is still in the worktree: `rm -rf` was denied in the first session, and in this one
    `mv … ~/osprey-runs/case-b-laurium-venv` asked for approval (the path is outside the session's working
    directory). ESLint in `make ci` reads its bundled JavaScript, and two `make test` cases name its files. Please
    move it: `mv OspreyFlow_Core/services/laurium/.venv ~/osprey-runs/case-b-laurium-venv`.
14. **Laurium's test environment imports the review queue and the registry** (review items 1 and 6): its test
    requirements now add asyncpg, jsonschema, pyproj and phonenumbers (the review store's own imports), and duckdb,
    networkx and rustworkx (`tests/conformance/registry.py` builds every port's factories at import). They are
    compiled with hashes from `laurium_test_requirements.in`, under Laurium's own pins as constraints, and
    installed `--require-hashes --no-deps`, never into the image.
15. **`ModelAdapterFactory` gains `offers` and `needs`** (`registry.py`): Laurium offers `extract` alone, so
    `test_suite.py`'s and `test_suite_vision.py`'s other cases skip it and say so (`factory.require(...)` at each
    case). Those two files are outside my map: a one-line call per case. **Request: ratify, or move it at merge.**
16. **`no_langchain_check --image` reads the image alone.** CI's image steps run it with the runner's own
    Python, which has no `pathspec`. The source leg now imports `tests/test_dockerignore.py`'s matcher and
    `tools/licence_check._instructions`, so it runs only in its own job (`make no-langchain-check`).

## Questions held (none stops the work; none is one of Prompt L's three)

1. **Three runs need an approving session** (tried again this round, each asked for approval): the built image
   refusing to start on a planted host (`docker run --rm -e OSPREY_LAURIUM_GATEWAY_URL=https://api.openai.com/v1
   case-b-laurium:p12`, expect exit 78 and the words); `tools.no_langchain_check --image` on the real Conduit and
   worker images and on a planted image (red then green); and `trivy image case-b-laurium:p12`. **Now kept out of
   `P12_CI.diff`** (review item 8) and carried, so no CI check that has never run is proposed.
2. **Rule 15: Laurium has never met a real gateway or model** (review item 1, the blocker). The live run is ready:
   Laurium is registered in `MODEL_PORT_ADAPTERS`, so `test_suite.py`'s two extract cases run on it against the
   stack's LiteLLM and the pinned conformance model. Its factory makes Laurium's scoped key on that gateway and
   deletes it in teardown, and fails if the service asks for any host but `litellm`. To run it, on the leased host
   in the lane's copy: `make -C OspreyFlow_Build laurium-env`, then from `OspreyFlow_Core`, with the lease's ports
   and `LITELLM_PORT`/`LITELLM_API_KEY` exported, `../OspreyFlow_Build/laurium-env/.venv/bin/python -m pytest -c
   ../OspreyFlow_Build/pytest.ini ../OspreyFlow_Build/tests/conformance/model_port/{test_suite.py,
   test_laurium_service.py,test_suite_extract.py} -k "extract or laurium"`. **Not run:** `stack_lease.sh acquire
   case-b … && stack_lease.sh live case-b` asked for approval. No lease was taken.
3. **The Superset image** is not given the image leg: it is a third-party image, and whether Superset 6.1 brings
   LangChain was not checked. If it does, Amendment 6's "no image without Laurium carries LangChain" needs its
   exception named.

## The lane-reviewer's round (about 08:10 UTC)

Run on the branch against the brief and rules 1–15. Verdict: do not merge. Every finding fixed, each refusal's test
written first and each fix planted red (`P12_RED_RECORD.md`: 45 offline, 9 in Laurium's environment, all red):

1. *"The lane's agent is still writing in the worktree"* — that was this session, writing the red record and this
   log while the review read; both committed in the commit after ef2f219f. No other agent works here (rule 14).
2. **The start check could be bypassed**: two spellings of one name (the last read hid the first; the libraries read
   either), the resolver's `LOCALDOMAIN`/`RES_OPTIONS`/`HOSTALIASES`, and `OPENAI_LOG` (a debug log of each request,
   a document's text with it). Fixed: every spelling read; those settings refused.
3. **The OpenAI client's own two retries** spent three of an engine's requests on one refused limit. Off now
   (`with_options(max_retries=0)` on Laurium's model's clients); the live test counts the gateway's requests.
4. **The image gate's tool was installed without hashes.** Now `licence-gate.txt`, compiled with hashes.
5. **`no_langchain_check` missed shapes**: a continued line, a build argument, requirements files, a `!` negation in
   `.dockerignore`. Now every non-Laurium Dockerfile instruction and requirements file is read for the names,
   whatever installs them; negations refused. (The Superset image: still held, question 3.)
6. **Tests that could not fail for their reason**: the adapter's words (now the exact forwarded 429 shape), Laurium's
   own folder (now its requirements copied in), an answer breaking `minLength` (now in the suite, reaching the
   adapter's own check).
7. **The real service's 401 and 413** are now sent to the real app, and planted.
8. **Answers of another shape** escaping untyped: now `ExtractionFailedError`, tested.
9. **The ADR and comments overstated**: decision 1 (what was shown red), decision 6 (constraints within a type are not
   given to Laurium's model; the adapter checks the whole schema; combinators beside a type now refused), decision
   7 (recorded entries now admit only "no readable licence, or MIT's text", never an LGPL or anything else), and
   `requirements.in`'s comment.
10. **Weak tests**: the unreachable-gateway case now closes the port with `litellm` still resolving; the findings
    test's store is a stand-in by design, said in the record.
11. **`pyproject.toml`**: a mypy override only. **Request to the orchestrator**: accept it, or move it at merge.

## The orchestrator's review of a5fa3c1b (not mergeable): each item

Fixed in ca85e385…283cfeb7, each new refusal's test red before its fix, each plant at its real call site
(`P12_RED_RECORD.md`: 53 offline and 14 in Laurium's environment, all red).

1. **Real gateway and model.** The stand-in now accepts LiteLLM's `/v1` base, served by LiteLLM as the bare
   route, which the in-process stand-in alone refused (`stand_in_http.py`; both bases asked). Planted: the stand-in
   as it was, 7 failed. Laurium is registered in `MODEL_PORT_ADAPTERS`, and `test_suite_extract.py` keeps only
   the refusals the real gateway cannot be made to give on demand. Decision 12 is corrected. **The leased live run
   was not taken:** the lease asked for approval (question 2), so the blocker stands.
2. **Gates.** The venv could not be moved (decision 13). `stack_lease.sh offline case-b` asked for approval.
   `make test` and `make -k ci` ran at 283cfeb7, directly in this worktree with the closed ports, as the first
   gates did. `make test` also ran once at 1b7c2a8c, where it found one failure of mine, fixed at 283cfeb7. Each
   run's output is recorded in full under "Built".
3. **Rule 1.** It was not kept for the extract suite: committed at 889cbf09, after `app.py` (d7defe10) and
   `adapter.py` (bc6e92d2). Said plainly in the red record; history not rewritten.
4. **Another host refused at the call that picks it.** `resolve_litellm_here` now refuses every name but
   `litellm` and keeps it. Planted: `openai_api_base` removed, 8 failed, `['api.openai.com'] == []`.
5. **Rule 15's second clause.** Each refused schema has `required` and is matched by its own words. Planted: the
   non-string-enum refusal removed, 3 failed.
6. **Rule 5's named test.** It now runs through the real `ExtractionCandidateStore`'s `pending` write, both over
   the fake service and over the real service in-process. Planted: the store promoting, red in both. Only
   asyncpg's pool is stood in for, so Postgres's acceptance of the row is not proven; the ADR draft says so.
7. **The master key.** Laurium's own scoped key (`keys.py`) for local and unrouted calls. A test reads every byte
   the adapter sends for each kind of call. Four plants red. **A credential step: two review rounds.**
8. **CI checks never run.** `docker run` and `trivy` asked for approval, so all three are out of `P12_CI.diff`
   and carried.
9. **Schema mapping.** All 13 distinct entity types, in 33 cases (default 10, fibo 11, niem 12, each pack composed on the default), map and round-trip, each alone and all
   together. None needed fixing.
10. **Files outside the map.** The rows ratified. The mypy override is narrowed to `services.laurium.app`
    (`disable_error_code`, since `ignore_missing_imports` matches the imported name wherever it is imported).
    `ADR_RESERVATIONS.md` is put back as main has it. New outside the map: one `factory.require` line per case in
    `test_suite.py` and `test_suite_vision.py` (decision 15).
11. **Minor.** Laurium's test requirements are compiled with hashes and installed `--require-hashes --no-deps`
    (`P12_MAKEFILE.diff`, now a `laurium-env` target). `no_langchain_check` uses `test_dockerignore`'s matcher and
    `licence_check._instructions`. `registry.py`'s re-export is dropped. `import_app` puts `os.environ` back. The
    stale figures are fixed. The proxy hazard is in the ADR draft (decision 4).

## Built

*First round:* built at 310648a1 and a5fa3c1b; gates `gates/310648a1.test.txt` and `gates/a5fa3c1b.ci.txt` (their
summaries only). The orchestrator's review of a5fa3c1b: not mergeable (the section above).

**Built at 283cfeb7** (the review's fixes, ca85e385…283cfeb7). Main has not moved (459ae1d4), so there was no
rebase. The gates ran once at that head, **directly in this worktree, not through `stack_lease.sh offline`**, which
asked for approval. Closed ports were pinned (`ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993
CLICKHOUSE_HTTP_PORT=59994`), with no lease and no stack. Each run's full output is kept:

- **`make -k test live-collect`**, `gates/283cfeb7.test.txt`: **4 failed, 11033 passed, 13 skipped** (37 min 49 s);
  live-collect imported every live file, `test_suite.py`'s 12 cases with Laurium's among them.
  1. `test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: `'pass' == 'skip'`,
     this host's own GPU. The branch touches nothing in the harness's preflight.
  2. `test_valkey_config.py::test_the_deployments_own_valkey_is_reached_plainly`: `{'port': 59993} != {'port':
     6379}`. The test reads `VALKEY_PORT`, pinned to the closed 59993 for an offline run. The branch touches nothing
     in `services/api` but the review store's tests.
  3. `test_connectors_are_carried_into_the_image.py::test_nothing_the_conduit_image_carries_execs_git` and
  4. `…::test_no_conduit_module_loads_a_path_under_tests`: every path named is under
     `services/laurium/.venv/`, the untracked scratch environment I may not move (decision 13); no tracked file is
     named. They pass once it is moved.
- **The same at 1b7c2a8c**, `gates/1b7c2a8c.test.full.txt`: those four and a fifth, mine:
  `test_test_file_coverage_check.py::test_no_new_drift_beyond_the_allowlist`. `test_findings_inferred.py`
  imported `asyncpg` (a live-service marker) for its pool stand-in's refusals, though it opens no connection. Fixed
  at 283cfeb7: the refusals are read from `review_queue.py`.
- **`make test-js`** (the `test` recipe's last line, which does not run once its first fails), `gates/283cfeb7.test-
  js.txt`: **1 failed, 3052 passed**. `MatrixView.budget.test.tsx` opened in 3389 ms against its 2500 ms budget
  while the server's load average was 9. (A pass on a rerun was claimed here and is withdrawn: it was never
  recorded. The gates at the rebased head supersede this run.) The branch touches nothing under `apps/`.
- **`make -k ci`**, `gates/283cfeb7.ci.txt`: failed only in `core-check`. Ruff passed, mypy found no issues in 450
  files, and all eight image scans passed, the workspace's included (the libxslt finding of a5fa3c1b is gone). Every
  Build target after it passed, `licence-check` and `test-file-coverage-check` among them:
  1. `lint` (ESLint): 6 errors, all in `services/laurium/.venv/…/urllib3/contrib/emscripten/
     emscripten_fetch_worker.js`, the untracked venv.
  2. `trivy` (Core's filesystem scan): 7 targets, CRITICAL `secrets` (gcp-service-account), all 7 under
     `services/laurium/.venv/` (the Anthropic SDK's docstrings), the same venv.
  3. `harness-a11y`: "this checkout is a linked worktree and OSPREY_PORTS_SLOT is not set". Run straight after
     with case-b's slot (`OSPREY_PORTS_SLOT=3 make harness-a11y`): **34 passed**, `gates/283cfeb7.a11y.txt`.
- **The red record at 283cfeb7**, `gates/283cfeb7.plants.txt`: 53 of 53 red offline (green start 205), 14 of 14
  in Laurium's environment (green start 26).

`make ci`'s OpenTofu check added this host's provider hashes to three `.terraform.lock.hcl` files. Not the branch's:
put back by path, never committed.

**Not run, each refused** (asked for approval this unattended session cannot give): the leased live run (the
review's blocker, question 2), `docker run` of the image and `trivy` on it (question 1), moving the venv (decision
13), `git apply --check` of the two diffs (checked by hand against the files' context lines), and `graphify
update`. Nothing of this session is still running: no agent was started, and every make run has ended. No container
was started; the image `case-b-laurium:p12` stays. The report is `REPORT.md`.

## Round 2, on the Mac (11 November, from about 13:30 UTC): the orchestrator's round-2 findings

The session moved to the Mac (`~/dev/osprey-wt/case-b`, the server's work fetched at 3215922); the owner was at the
Mac and approved each `stack_lease.sh` call. Rebased onto main 8aa3da5 (one conflict: both sides appended to
`06_DECISIONS.md`; both kept, main's first, nothing of main's removed).

1. **The leased live run (blocker 1).** No leased stack has a model gateway (`lane_stacks.tsv`), so the
   orchestrator stood up CI's pinned LiteLLM (its own Postgres, keys real) and Ollama on the server; case-b ran
   under stack c's lease (`P12_RED_RECORD.md`, "Round 2"). **Open finding: Laurium has not yet read any real
   model's answer.** Its conforming-answer case failed 3 of 3 on the pinned `qwen2.5:0.5b-instruct`
   (`unparseable`); the LiteLLM adapter's same case passed on the same model. Ruled by the orchestrator: that case
   `xfail(strict=True, raises=ExtractionFailedError)` on Laurium alone (`test_suite.py`); part 2's exit gains
   Laurium reading a conforming answer from the client's own engine (P11 part 2's gateway or Bedrock route); D2c
   says Laurium is not yet shown on a real model until then.
2. **The scoped key at the real gateway (blocker 2).** `test_laurium_key_live.py` passed on the real gateway. Its
   plants: the master key at the adapter, red; Laurium's key made with `user_role: proxy_admin`, green, **so that
   plant cannot be shown red on the pinned LiteLLM**: no field of the key's request is known to grant an admin
   right. On the real gateway the master-key plant is caught first by the token-is-the-key-held check, **so the
   four admin-route assertions are shown red on the stand-in only**. The hosted-engine branch's master-key plant:
   `[gemini]` red offline (54 of 54).
3. **The gates (blocker 3)** through `stack_lease.sh offline case-b` at the head: `gates/<head>.{test,ci}.txt`.
4. **The image leg said carried** in the tool, its test, `P12_MAKEFILE.diff` and a new sentence in Amendment 6.
5. **Ownership** of `test_guard.py` and the `factory.require` lines, ratified: its own friction fragment
   (`2026-11-11-case-b-conformance-suite-ownership.md`); `test_suite.py`'s xfail is a further line in that file,
   by the same ruling.
6. **Minor:** 13 distinct entity types in 33 cases; the unrecorded MatrixView rerun withdrawn; `test_suite_extract`'s
   scope said truly. **Carried:** `review_queue.py`'s asyncpg import (it satisfies the drift check by reading the
   refusals from a module, not by the gate's own rule), `extract_engines.py` duplicating `ModelAdapterFactory`, and
   `laurium_in_process.py`'s teardown deleting whatever Laurium key the gateway holds (a part 2 hazard: run against a
   deployment's gateway it would delete the deployment's key; `test_laurium_key_live.py` refuses such a gateway
   before writing, the suite's factory does not yet).
7. **The lane-reviewer's round on round 2** (13 findings) fixed before the lease: the live test gated off CI and
   unleased gateways, given a positive control and a known-key check, every removal run and leftovers found by tag,
   the `--live` mode refusing without a gateway; `plants_P12.py` counting an empty green start as green (found on
   the server, fixed).
