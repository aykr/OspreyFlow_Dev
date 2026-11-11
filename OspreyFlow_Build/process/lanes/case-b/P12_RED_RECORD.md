# case-b · P12 part 1 · the red record (rule 15)

Every refusal and rule P12 part 1 adds was shown red at its real call site by `plants_P12.py`, each plant put back
after. It needs a green start, and counts a plant red only when pytest reports failed tests and no error. On the test
server, 11 November 2026, at ef2f219f, offline with the closed ports (59991-59994), no lease, no container.

- **Offline** (the Conduit's 3.12 environment): 33 plants, 33 red.
- **In Laurium's own 3.13 environment** (`make laurium-service`'s, built by hash): 6 plants, 6 red; the service's real
  code with Laurium 0.6.0, LangChain and the OpenAI client, every call over real HTTP to the gateway's stand-in.

The tests came first: `test_settings.py` and `test_schema_map.py` failed at collection before the modules existed;
`test_recorded_licence_evidence.py` 5 failed (8 passed: the rows really fail the gate without their entries) before
the entries existed; `test_licence_gate.py` 11 failed against the recogniser's gate copied unchanged;
`test_no_langchain_check.py` 2 failed (the real tree: `.dockerignore` did not yet leave `services/laurium` out).

**Found by the plants, fixed before recording** (rule 15's second clause): two cases passed for another reason.
*An item allowed properties it does not declare* stayed green: the planted item also lacked a required property, so
it was refused for that; the test now fills every property first and shows the complete item accepted.
*An object allowing undeclared properties* stayed green: the planted schema had no `required`, so the top-level rule
refused it; the case now declares it. A third plant, *the gateway's words passed on* by the adapter alone, stayed
green because the service never forwards words but a 429's error: the guarantee is two layers, so its plant is now
both (the service forwarding every error, the adapter repeating it), and is red. And one fault in the runner itself:
a plant changing `0.14.0` to `0.15.0`, put back in the same second, left its `.pyc` standing (same size and mtime),
so the next run read the plant; the runner now writes no bytecode and bumps a restored file's mtime.

## Offline

| Plant | Red |
| --- | --- |
| a gateway URL of any host accepted | 3 failed, 41 passed |
| a credential in the gateway URL accepted | 1 failed, 43 passed |
| a path or a query on the gateway URL accepted | 2 failed, 42 passed |
| a gateway URL with no port accepted | 1 failed, 43 passed |
| HTTPS_PROXY not read | 2 failed, 42 passed |
| AWS's endpoints not read | 2 failed, 42 passed |
| LangSmith tracing on accepted | 5 failed, 39 passed |
| an unknown OSPREY_LAURIUM_ setting ignored | 1 failed, 43 passed |
| a setting's value repeated in the words | 1 failed, 43 passed |
| an enum given as any string | 1 failed, 17 passed |
| an item allowed properties it does not declare | 1 failed, 17 passed |
| a top-level property not required accepted | 1 failed, 17 passed |
| an object allowing undeclared properties accepted | 1 failed, 17 passed |
| an optional property's null kept in the output | 1 failed, 17 passed |
| a description's braces left single | 1 failed, 17 passed |
| the request's schema not checked before the call | 1 failed, 14 passed |
| the answer trusted without the request's schema | 1 failed, 14 passed |
| an engine's call sent with the master key | 2 failed, 13 passed |
| an engine's call sent untagged | 2 failed, 13 passed |
| a limit's refusal not read as a limit | 1 failed, 14 passed |
| a model not offered not told apart | 1 failed, 14 passed |
| a finding traced to another document | 1 failed |
| a recorded entry admitting any version | 3 failed, 10 passed |
| a recorded entry admitting a declared GPL | 1 failed, 12 passed |
| a recorded name matched only as spelt | 1 failed, 12 passed |
| the recorded entries not consulted | 4 failed, 9 passed |
| the image gate letting the encoder's packages through | 6 failed, 12 passed |
| the image gate's entries parting from the repository's | 2 failed, 16 passed |
| Laurium's folder left in the Conduit's context unnoticed | 1 failed, 17 passed |
| LangChain or Laurium in the Conduit's lock unnoticed | 2 failed, 16 passed |
| another Dockerfile installing LangChain unnoticed | 1 failed, 17 passed |
| an image's LangChain unnoticed | 8 failed, 10 passed |
| an unreadable image passed | 1 failed, 17 passed |

## In Laurium's environment (`test_laurium_service.py`, `test_suite_extract.py`)

| Plant | Red |
| --- | --- |
| the service serving with a refused setting | 4 failed, 8 passed |
| a gateway refusal answered as Laurium's row of Nones (`BatchExtractor`'s own failure shape) | 4 failed, 18 passed |
| the gateway's words passed on, by the service and the adapter | 2 failed, 10 passed |
| an unparseable answer asked once | 1 failed, 11 passed |
| the call's tag not sent to the gateway | 1 failed, 11 passed |
| a description's braces left single, through the real prompt | 11 failed, 11 passed |

## Not shown red here, and why

- **The built image's own refusal to start, and the image leg of `no_langchain_check` on a real image.** Both need
  `docker run`, which this unattended session may not run (it asks for approval; `docker build` it may). The
  service's start check is the same code, imported as the image imports it, and shown red above; the image leg's
  reader is shown red on its script's real output. Held: SERVER_LOG.md, "Questions held".
- **The Laurium image's trivy scan**: `trivy` likewise asks for approval here. In the CI diff (`trivy-image-laurium`).
