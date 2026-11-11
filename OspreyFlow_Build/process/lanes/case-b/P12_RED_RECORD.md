# case-b · P12 part 1 · the red record (rule 15)

Every refusal and rule P12 part 1 adds was shown red at its real call site by `plants_P12.py`, each plant put back
after. It needs a green start, and counts a plant red only when pytest reports failed tests and no error. On the test
server, 11 November 2026, after the orchestrator's review of a5fa3c1b (its fixes in ca85e385…283cfeb7), offline with
the closed ports (59991-59994), no lease, no container; run at 1b7c2a8c and again at 283cfeb7, the same counts
(`gates/283cfeb7.plants.txt`).

- **Offline** (the Conduit's 3.12 environment): green start 205 passed; **54 plants, 54 red** (53 on the server;
  round 2's plant on the hosted engine's branch added and the whole set rerun on the Mac at 73d3f080, offline with the
  closed ports, no lease, `gates/73d3f080.plants-offline-round2.txt`).
- **In Laurium's own 3.13 environment** (built by hash, `laurium-env`): green start 26 passed (`test_laurium_service.py`
  17, `test_suite_extract.py` 4 × 2 engines, `test_laurium_findings_pending.py` 1); **14 plants, 14 red**. The
  service's real code with Laurium 0.6.0, LangChain and the OpenAI client in-process, every model call over real HTTP
  to the gateway's stand-in served as `litellm` on 127.0.0.1, every other name refused at the lookup.

(Before this round: 45 offline and 9 in Laurium's environment, green starts 156 and 26 = 14 of the service and
12 of the suite, 6 cases × 2 engines.)

## Rule 1: was the extract suite written before the adapter and the app? No.

`git log --reverse --name-status 459ae1d4..HEAD`, the commits that add the three:

| Commit | Time (UTC) | Adds |
| --- | --- | --- |
| d7defe10 | 06:57 | `services/laurium/app.py` (with the service's settings, schema map and their tests) |
| bc6e92d2 | 06:57 | `packages/adapters/extract_laurium/adapter.py` (with its offline tests) |
| 889cbf09 | 06:58 | `tests/conformance/model_port/test_suite_extract.py`, `test_laurium_service.py`, `extract_engines.py` |

**The extract suite was committed after both `adapter.py` and `app.py`.** Nothing in the history shows the suite
existing, let alone failing, before the adapter it defines. The first record's "the tests came first" was true of
`test_settings.py`, `test_schema_map.py`, the licence tests and `test_no_langchain_check.py` (each run red against a
missing or unchanged module in the session), and not of the conformance suite: rule 1 was not kept for it. History is
not rewritten. In this round every new refusal's test was run red before its fix (below).

## This round's tests, red before their fix

- `test_adapter.py`, the scoped key (item 7): 5 failed against the adapter as it was (a local and an unrouted call
  sent the master key; `test_no_call_from_the_adapter_carries_the_master_key[None]` and `[local]` read the master key
  in the bytes sent; an empty master key not refused), then green with `keys.py`.
- `test_no_langchain_check.py`, the matcher and the image leg (item 11): 5 failed against the tool as it was (three
  other spellings that leave Laurium out refused, a pattern leaving part of it in not named, the source leg run in
  an image step), then green.
- `test_schema_map.py` (items 5 and 9): each refusal now matched by its own words; the 13 distinct entity types, in 33 cases (default 10,
  fibo 11, niem 12, each pack composed on the default), mapped green at once (none raised `UnsupportedSchema`, so none needed a fix or fixed words).

## Plants found green, and what was wrong (rule 15's second clause)

This round:

- *Every refused schema at `test_schema_map.py` ~146–158* (the orchestrator's item 5): the `oneOf`, `$ref`,
  type-list, bare object, bare array and non-string-enum cases had no `required`, so each was refused at the
  top-level `required` check before `_type` ran. Each now has `required` and is matched by its own words; the
  non-string-enum plant (`schema_map.py` ~97–98) is red, 3 failed.
- *Laurium's key made for every model*: the test's empty-`models` call used a client with no base URL, refused by
  httpx before the guard was reached. Now the client is the gateway's, the refusal matched by its words, and the key
  held is shown unchanged: red.
- *A `!` negation putting Laurium back*: once `.dockerignore` is read with the repository's matcher, the separate
  negation check was dead (the matcher already names the file the negation puts back), so its plant stayed green.
  The check is removed; the plant now is "a file a negation puts back not looked at": red.
- *The findings test* (the orchestrator's item 6): it swapped in a capturing store and ran over the fake service,
  so no plant in the real store's write could turn it red. Now it goes through the real `ExtractionCandidateStore`
  (below); the promoting plant is red in both environments.

From the first rounds (kept): an item missing a required property; an object allowing undeclared properties with no
`required`; the gateway's words, which only a 429 that is not a limit carries; a recorded entry admitting a GPL or
LGPL, refused first by the "no readable licence, or MIT's text" rule; and the runner's own stale bytecode (friction
row `2026-11-11-case-b-laurium-stale-bytecode.md`).

## Offline

| Plant | Red |
| --- | --- |
| a gateway URL of any host accepted | 3 failed |
| a credential in the gateway URL accepted | 1 failed |
| a path or a query on the gateway URL accepted | 2 failed |
| a gateway URL with no port accepted | 1 failed |
| HTTPS_PROXY not read | 3 failed |
| AWS's endpoints not read | 2 failed |
| LangSmith tracing on accepted | 6 failed |
| one spelling of a name read, the last | 3 failed |
| the resolver's own settings not read | 3 failed |
| a debug log of each request accepted | 3 failed |
| an unknown OSPREY_LAURIUM_ setting ignored | 1 failed |
| a setting's value repeated in the words | 1 failed |
| an enum given as any string | 1 failed |
| an item allowed properties it does not declare | 1 failed |
| a top-level property not required accepted | 1 failed |
| an object allowing undeclared properties accepted | 1 failed |
| an optional property's null kept in the output | 1 failed |
| a description's braces left single | 1 failed |
| a combinator beside a type given as the type alone | 3 failed |
| **an enum of anything but strings given to Laurium** (item 5) | 3 failed |
| the request's schema not checked before the call | 1 failed |
| the answer trusted without the request's schema | 1 failed |
| an engine's call sent without its own key | 4 failed |
| **a call for the deployment's own models sent with the master key** (item 7) | 5 failed |
| **a hosted engine's call sent with the master key** (round 2, item 2: `adapter.py`'s `call.engine != LOCAL` branch; `test_no_call_from_the_adapter_carries_the_master_key[gemini]` alone) | 1 failed |
| **Laurium's key derived from an empty master key** (item 7) | 2 failed |
| **Laurium's key made for every model** (item 7) | 1 failed |
| **Laurium's key derived as an engine's** (item 7) | 1 failed |
| **the review queue's write promoting a finding** (item 6, `services/api/review.py`) | 1 failed |
| an engine's call sent untagged | 2 failed |
| a limit's refusal not read as a limit | 1 failed |
| a model not offered not told apart | 1 failed |
| the gateway's words passed on by the adapter (a 429 not a limit) | 2 failed |
| an answer of another shape escaping untyped | 2 failed |
| a finding traced to another document | 1 failed |
| a recorded entry admitting any version | 3 failed |
| a recorded entry admitting a declared GPL | 1 failed |
| a recorded entry admitting a declared LGPL | 1 failed |
| a recorded entry admitting any other declared licence | 1 failed |
| the image's gate tool installed without hashes | 1 failed |
| a recorded name matched only as spelt | 1 failed |
| the recorded entries not consulted | 4 failed |
| the image gate letting the encoder's packages through | 6 failed |
| the image gate's entries parting from the repository's | 2 failed |
| Laurium's folder left in the Conduit's context unnoticed | 3 failed |
| **only the folder's own spelling read, not the matcher (as it was)** (item 11) | 5 failed |
| **a file a negation puts back not looked at** (item 11) | 1 failed |
| **the source leg run in an image step** (item 11) | 1 failed |
| LangChain or Laurium in the Conduit's lock unnoticed | 2 failed |
| another Dockerfile or requirements file naming LangChain unnoticed | 6 failed |
| requirements files not read | 2 failed |
| Laurium's own folder not passed | 7 failed |
| an image's LangChain unnoticed | 9 failed |
| an unreadable image passed | 1 failed |

## In Laurium's environment (`test_laurium_service.py`, `test_suite_extract.py`, `test_laurium_findings_pending.py`)

| Plant | Red |
| --- | --- |
| the service serving with a refused setting | 4 failed |
| a gateway refusal answered as Laurium's row of Nones (`BatchExtractor`'s own failure shape) | 4 failed |
| the gateway's words passed on, by the service and the adapter | 2 failed |
| the OpenAI client's own retries left on | 1 failed |
| a call without the gateway's token sent on | 1 failed |
| a text over the limit read | 1 failed |
| an unparseable answer asked once | 1 failed |
| the call's tag not sent to the gateway | 1 failed |
| a description's braces left single, through the real prompt | 13 failed |
| **the gateway not given to Laurium's chat model** (item 4: `openai_api_base` removed, `app.py` ~98) | 8 failed |
| **the lookup letting another name resolve** (item 4: the fixture itself) | 1 failed |
| **the gateway's /v1 route not served** (item 1: the stand-in as it was) | 7 failed |
| **a call for the deployment's own models sent with the master key** (item 7, through the real service) | 2 failed |
| **the review queue's write promoting a finding** (item 6, through the real service) | 1 failed |

The item 4 plant fails for its stated reason, read off the run: `test_every_model_call_goes_to_the_gateway_and_no_
other_host[/v1]` and `[]` each `AssertionError: assert ['api.openai.com'] == []`. Without `openai_api_base`,
Laurium's `create_llm` leaves the OpenAI client on its own default host; the fixture refuses that name at the
lookup and names it, so nothing left the machine (before this round the fixture let every other name resolve,
and the same plant would have sent a synthetic key towards `api.openai.com`).

## Item 6: what the findings tests prove

`test_findings_inferred.py` (Conduit, over the fake service) and `test_laurium_findings_pending.py` (Laurium's
environment, over the real service in-process) each run `run_extraction` with Laurium's adapter and the **real**
`ExtractionCandidateStore`: its own `store` builds each record and sends its own `INSERT`, and the row is read by
column as the store sent it (`status` `pending`, the document, the span that says "Lovelace", the analyst's unit;
the finding the document does not state never written). Only asyncpg's pool is stood in for (`review_queue.
CandidateRows`), refusing a NULL where the store's own `CREATE TABLE` says NOT NULL, values that do not match the
statement, and a repeated id (`test_the_pools_stand_in_refuses_what_postgres_refuses`). **They do not prove that
Postgres accepts the row**: that is `tests/services/api/test_review_store.py`'s, live. Said so in the ADR draft.

## Not shown red here, and why

Each needs a command this unattended session may not run: it asks for approval, which nobody can give here, and I
did not route around it (no `docker run` from inside a script, no other gateway).

- **Laurium against a real gateway and model** (item 1): `stack_lease.sh acquire case-b … && stack_lease.sh live
  case-b` asked for approval; **no lease was taken and no stack touched**. So the model's answer to Laurium's prompt
  has still never been parsed: Laurium has never met a real gateway or model. The leased run (`make -C
  OspreyFlow_Build laurium-env` on the host, then `test_suite.py`, `test_laurium_service.py` and
  `test_suite_extract.py` in Laurium's environment with the stack's ports) is carried.
- **The built image refusing to start on a planted host, the image leg of `no_langchain_check` on the real Conduit
  and worker images, and `trivy image` on Laurium's image** (item 8): `docker run` and `trivy` each asked for
  approval. Kept out of `P12_CI.diff` and carried.
