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
- **Proven through the gateway's stand-in**: in Laurium's own 3.13 environment (built by hash by the new
  `make laurium-service`), the service's real code with Laurium 0.6.0, LangChain and the OpenAI client, every
  call over real HTTP to the measured stand-in served as `litellm`: 22 passed (12 of the service, 10 of the suite,
  5 cases on each engine). In the Conduit's environment the suite's 5 LiteLLM cases pass and the 5 Laurium cases
  skip with their reason.
- **Red record** (`P12_RED_RECORD.md`, `plants_P12.py`): 33 offline plants and 6 in Laurium's environment, all
  red. Two tests were found passing for another reason and fixed; a stale-bytecode fault in the plant runner found
  and fixed (friction row `2026-11-11-case-b-laurium-stale-bytecode.md`).

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
5. **The gateway token travels with each call**, from the adapter to the service in `Authorization`: the engine's
   own key (derived in the Conduit, as the LiteLLM client derives it) or the master key; with the call's tag. The
   service keeps no key. So per-engine limits and usage apply to Laurium's calls as to Deep read's (planted red).
6. **Schema subset.** Every top-level property must be required (Laurium's model makes every field required); an
   object may not say `additionalProperties: true`; left unsaid, extras are allowed by the schema but refused in
   the answer (stricter). Laurium reports no span: spans are located in the text by `services/extract/
   candidates.py`, as for Deep read, and a finding the text does not contain is dropped there.
7. **The OpenAI client's own retries kept.** Laurium's `create_llm` does not expose `max_retries`, so a 429 or 5xx
   is retried twice by the client before the service answers: a limit costs three refused calls at the gateway.
   Harmless (a refused call spends nothing), noted.
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
12. **"Proven on local-lite"** read as: through the stand-in served as `litellm`, as local-lite's network names
    the gateway. Rendering the service into the local-lite compose is left to part 2 with the setting that
    chooses it (`render.py` is platform's; "built only when chosen" needs the choice).
13. **The scratch environment** I made to read Laurium's source (`OspreyFlow_Core/services/laurium/.venv`,
    untracked) could not be removed: `rm -rf` was denied. ESLint in `make ci` reads its bundled JavaScript (6
    errors, none in the branch). Please remove it.

## Questions held (none stops the work; none is one of Prompt L's three)

1. **Three runs need an approving session**: the built image refusing to start on a planted host
   (`docker run --rm -e OSPREY_LAURIUM_GATEWAY_URL=https://api.openai.com/v1 case-b-laurium:p12`, expect exit 78
   and the words); `tools.no_langchain_check --image` on the real Conduit and worker images and on a planted image
   (red then green); and `trivy image case-b-laurium:p12`. All three are in the CI diff.
2. **Rule 15: Laurium's exact request has not met the real gateway.** The stand-in is measured against the pinned
   LiteLLM for the Conduit's own requests; LangChain's `ChatOpenAI` sends `temperature`, `stream: false` and the
   tag in `metadata`. LiteLLM takes OpenAI parameters, but this is not measured. Proposed: one leased live check
   (`stack_lease.sh live case-b`) sending Laurium's request through the stack's real gateway, before part 2.
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

## Built

**Built at 310648a1** (the reviewer's findings fixed), and at **a5fa3c1b** with the service inventory's row, which
make test found missing. Gates at those heads: `gates/310648a1.test.txt`, `gates/a5fa3c1b.ci.txt`, every failure
explained. Main has not moved (459ae1d4), so there was no rebase. The orchestrator's independent review starts when it
is back; I am not reporting ready-to-merge until it has run. Nothing of this session is still running: the reviewer
agent has finished, and so have the make runs. No container is left (only `docker build` was run; the image
`case-b-laurium:p12` stays for the held `docker run` check). The report is `REPORT.md`.
