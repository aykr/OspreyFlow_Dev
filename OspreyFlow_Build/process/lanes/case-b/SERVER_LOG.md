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
  sha256 `1932429d…0fb85`. Read Laurium 0.6.0's source from its wheel (installed `--no-deps` into a
  gitignored scratch venv, `services/laurium/.venv`; nothing of it run).

## Decisions taken (the owner may overrule each)

1. **No heartbeats from the server.** `lanes_heartbeat.sh` reports to the orchestrator's session, which is
   offline; this log stands in for them.
2. **The Laurium service calls Laurium's chain directly, not `BatchExtractor.process_chunk`.** Read in
   Laurium 0.6.0's `decoder_models/extract.py`: `BatchExtractor` catches every failure of a row (a refused
   key, an unknown model, unparseable output) and returns that row with **every field `None`**, logging
   the reason. Through a DataFrame that is a silent empty finding, which rule 2's spirit and rule 5 forbid
   (an analyst would see "found nothing" for "the gateway refused"). The service builds the
   `BatchExtractor` (Laurium's own prompt, parser and chain) and awaits its documented `chain` attribute
   for the one document, so a refusal arrives as itself. Options were: `process_chunk` and treat an
   all-`None` row as failure (loses the reason, and a document with genuinely nothing to find in a
   one-field schema is indistinguishable), or our own LangChain chain (no longer Laurium). Chose the
   chain: it is Laurium's, and it fails honestly.
3. **Laurium's `create_llm` only with `llm_platform="openai"` and `openai_api_base` the gateway.** Its
   other platforms (`ollama`, `bedrock`, `anthropic`) each reach their own host, so the service's settings
   name no platform at all: the one it uses is fixed in code, and the base URL's host must be the
   gateway's (`OSPREY_LAURIUM_GATEWAY_HOSTS`, default `litellm`), refused at start otherwise.

## Questions held (none stops the work)

(none yet)

## Built

(not yet)
