# Rules-b lane · brief guides · the guides from Home, by the places a person may open (S)

Written by the orchestrator, 12 November 2026, at the owner's request, for a **fresh rules-b session on `sol`**,
from **main** (`git fetch`, branch `lane/rules-b-guides` from `main`). Read ADR-115 E3, ADR-145 decision 1 and
N6, `apps/workspace/src/home/HomePage.tsx` and the four guides in `OspreyFlow_Core/docs/` first. Opus, medium.
Size S.

**The owner's words:** on the landing page after sign-in, a link to the user guide, the developer guide and the
administration guide under the different interfaces, so new people read the documentation from their own
sign-in rather than being sent the guides; only the guides the signed-in person's profile allows.

**The lane, the stacks, the merge rule.** Test stacks are on the owner's server only (b to g); Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator for a stack, then main's `stack_lease.sh` (acquire, up, `remote rules-b -- …`, down, release; `remote-log rules-b` reattaches). `make test` runs on the server: `stack_lease.sh offline rules-b -- make test` (it runs pytest, live-collect and test-js in turn; test-js also on the Mac, where Node is). Ask before `make -k ci` or any Playwright here (two heavy runs at most). Never call remote or offline while one of your runs is alive. Prompt L's rules: never stop on a question; build the recommended option (the strict one for access) and log it under "Decisions taken"; real data stops a piece. Your own lane-reviewer, then the gates at a commit rebased onto main, saved under `gates/`, raw, not filtered, with one leased live run including `test_route_rights.py`; re-gate after any code change. Report to the orchestrator **by message**.

**The orchestrator's rulings (recommended options, listed for the owner to overrule):**
- **Which guide, where:** under Home's **Glass** card, the *User guide*; under **Ingest Studio**, the
  *Developer guide* (its own first lines: "For data engineers"); under **Admin**, the *Administration guide*. A
  guide appears only with a card the person's rights already open (ADR-145 decision 1 and N6: no card, no
  guide). The architecture guide is not linked.
- **Served by the Conduit, checked on the server, never a static link:** `GET /v1/guides/{user|developer|administration}`
  returns the deployment's own PDF (`OspreyFlow_Core/docs/pdf/*.pdf`, the version it was built with) only to a
  principal holding the right that opens that place, and 403 (in words) otherwise, the same check the place's
  own gate uses. An access-control test for each guide and each role (rule 4), `test_route_rights.py` rows for
  the new route, and a test that the PDF served is byte for byte the file in the image. The Conduit's image must
  carry `docs/pdf/` (`services/api/Dockerfile`: if that file is not yours, a diff for the orchestrator).
- **In the Glass:** a plain link under each card's own words ("Read the user guide (PDF)"), opening the PDF
  in a new tab through the route with the person's token (a fetch then a blob URL, so no token in a URL).
  Keyboard (rule 13): a step in the home harness's keyboard spec reaching and activating each link; axe in
  dark, light and GOV.UK; tokens only (tokens.css), British English.
- **ADR-145 Amendment 10 is reserved for you:** write it as built, with the test that would fail for each
  sentence (rule 12). The user guide's "Home" section and the admin guide gain a line each (as diffs for docs,
  who owns them).

**Gates:** as every step: make -k ci and make test on the server, live-collect's result, test-js, a11y and
keyboard on the Mac, the route's live access case under a lease; plants for the right check (a principal
without the place's right fetching the guide), the byte-for-byte check, and the hidden link.

**Never.** osprey-small (the owner's demo deployment, v0.5.0, frozen) and its containers are never touched by
this step: throwaway lane stacks only. Nothing of this step runs on the server from **12:00 UK on Friday 13
November** until the owner says the demo is over. Not pushed; the orchestrator merges. Into v0.5.1 with the
chain. The owner holds the osprey-small rebuild until this step has landed.
