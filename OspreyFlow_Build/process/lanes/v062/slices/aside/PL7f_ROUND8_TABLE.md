# PL7f, round 8: every open case (the conductor, 25 November 2026, 08:04 UTC)

From the round-7 verifier's record (tip `eb38b94d5c`). **This round is the one row below and nothing else.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **The administration guide contradicts itself on the pages setting.** Brief item 5 and the owner's condition 1 (a release blocker) ask that every PL7a2b sentence saying the setting turns the page service on be reworded: the setting exists, is off, and is not for use. Appendix A's row for the `pages` section still says it is "off, and turned on for one deployment at a time by the owner", directly above the reworded `pages.enabled` row ("it is not for use yet, and nothing is switched on by it for a deployment you run"). | `OspreyFlow_Core/docs/administration-guide.md` Appendix A (and the guide's PDF and manifest, made again from the source) | Both rows say the same thing in your reworded words. **Read the whole guide and every other document the release ships** (`OspreyFlow_Core/docs/`) for any other sentence that says the setting is turned on or for use, and reword each the same way; say in your report each place you read and what you changed. A test fails if a shipped document says the pages setting is turned on, enabled for a deployment, or for use (red first against today's Appendix A row). |
