# PL7f, round 6: every open case (the conductor, 25 November 2026, 06:54 UTC)

From the round-5 verifier's record (tip `84efc67c7c`). The finding names sign-in, so it is the owner's: fixed, never
accepted narrower. **This round is the one row below and nothing else.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **The page service's own sign-in client is not in the setting-off pin.** Round 4 item 2 pinned every identity and sign-in address rendered with `pages.enabled` off against main's own output, but `realm.pages_client` is left out; its setting-off branch (`else page_addresses.client_origin(config)`, `OspreyFlow_Core/harness/realm.py` about lines 432 to 437) is the one sign-in address this part newly wrote, and no test would fail if it changed. The code is right today. | the setting-off pin test | The pin includes the page service client's redirect URIs, web origins and post-logout address with the setting off, for every shape and for an origin written with and without a default port, compared with what main's merge-base renders (a reference taken from it, not written by hand). Red first: a planted change to that `else` branch (for example `derive`'s normalised origin in its place, the shape round 2 had) must turn the pin red. |
