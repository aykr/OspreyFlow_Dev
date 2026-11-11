# case-b · P12 part 1 · the red record (rule 15)

Every refusal and rule P12 part 1 adds was shown red at its real call site by `plants_P12.py`, each plant put back
after. It needs a green start, and counts a plant red only when pytest reports failed tests and no error. On the test
server, 11 November 2026, after the lane-reviewer's round, offline with the closed ports (59991-59994), no lease, no
container.

- **Offline** (the Conduit's 3.12 environment): green start 156 passed; **45 plants, 45 red**.
- **In Laurium's own 3.13 environment** (`make laurium-service`'s, built by hash): green start 26 passed; **9 plants,
  9 red**. The service's real code with Laurium 0.6.0, LangChain and the OpenAI client, every call over real HTTP to
  the gateway's stand-in.

The tests came first: `test_settings.py` and `test_schema_map.py` failed at collection before the modules existed;
`test_recorded_licence_evidence.py` 5 failed (8 passed: the rows really fail the gate without their entries) before
the entries existed; `test_licence_gate.py` 11 failed against the recogniser's gate copied unchanged;
`test_no_langchain_check.py` 2 failed (the real tree: `.dockerignore` did not yet leave `services/laurium` out). In the
review round each new refusal's test was written before its fix, and failed first.

## Plants found green, and what was wrong (rule 15's second clause)

- *An item allowed properties it does not declare*: the planted item also lacked a required property, so it was
  refused for that. The test now fills every property and shows the complete item accepted first.
- *An object allowing undeclared properties*: the planted schema had no `required`, so the top-level rule refused it.
- *The gateway's words passed on* by the adapter alone: no test sent the one shape that carries words (a 429 that is
  not a limit, its error forwarded). The test now sends that exact shape; the adapter-only plant is red, and the
  two-layer plant (the service forwarding every error too) stays as a second row.
- *A recorded entry admitting a declared GPL / LGPL*: once entries admit only "no readable licence, or MIT's text",
  a bare `GPL-3.0` is refused by that rule before the GPL rule. The cases that need the GPL and LGPL rules are MIT
  beside another licence (`MIT AND GPL-3.0-or-later`, `MIT AND LGPL-3.0`); planted on those, red. (`MIT OR LGPL-3.0`
  is admitted by the register's own rule, one allowed alternative under OR, and is not a case.)
- **The runner itself**: a plant changing `0.14.0` to `0.15.0`, put back in the same second, left its `.pyc`
  standing (same size and mtime), so the next run read the plant. The runner now writes no bytecode and moves a
  restored file's mtime on (friction row `2026-11-11-case-b-laurium-stale-bytecode.md`).

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
| a combinator beside a type given as the type alone | 1 failed |
| the request's schema not checked before the call | 1 failed |
| the answer trusted without the request's schema | 1 failed |
| an engine's call sent with the master key | 2 failed |
| an engine's call sent untagged | 2 failed |
| a limit's refusal not read as a limit | 1 failed |
| a model not offered not told apart | 1 failed |
| the gateway's words passed on by the adapter (a 429 not a limit) | 1 failed |
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
| Laurium's folder left in the Conduit's context unnoticed | 1 failed |
| Laurium put back into the Conduit's context by a negation unnoticed | 1 failed |
| LangChain or Laurium in the Conduit's lock unnoticed | 2 failed |
| another Dockerfile or requirements file naming LangChain unnoticed | 6 failed |
| requirements files not read | 2 failed |
| Laurium's own folder not passed | 4 failed |
| an image's LangChain unnoticed | 8 failed |
| an unreadable image passed | 1 failed |

## In Laurium's environment (`test_laurium_service.py`, `test_suite_extract.py`)

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
| a description's braces left single, through the real prompt | 12 failed |

## Not shown red here, and why

- **The built image's own refusal to start, and the image leg of `no_langchain_check` on a real image.** Both need
  `docker run`, which this unattended session may not run (it asks for approval; `docker build` it may). The
  service's start check is the same code, imported as the image imports it, and shown red above; the image leg's
  reader is shown red on its own script's real output. Held: SERVER_LOG.md, "Questions held".
- **The Laurium image's trivy scan**: `trivy` likewise asks for approval here. In the CI diff (`trivy-image-laurium`).
- **The candidates' `pending` status** (`test_findings_inferred.py`): its store stands in for
  `ExtractionCandidateStore`, whose `pending` write is live-tested in `tests/services/api/test_review_store.py`; the
  test shows Laurium's findings reach that store as located candidates, and nothing else.
