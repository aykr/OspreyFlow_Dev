# PL7c: round 9, the ratchet after PL12b (24 November 2026, 06:45 UTC; the conductor, on the owner's send-back)

**The owner's rule: no round from 5 on starts without a table of every open case.** **No case is open: every case raised in rounds 1 to 8 is closed (the last verifier passed `e2d9b65b10`).** This round exists for one thing that happened after: **PL12b has merged (`fb972ec`)**, and with it main has a ratchet on the GOV.UK rules that live outside a theme folder.

| # | Case | Status |
| --- | --- | --- |
| 1 | **The ratchet.** PL12b's allowlist (`OspreyFlow_Build/tests/fixtures/theme_rule_allowlist.txt`, its count on the first line) lists the GOV.UK rules outside a theme folder. On the server, a tree with PL12b's change and yours failed five of PL12b's tests (`test_the_real_tree_passes_with_the_allowlist`, `test_the_allowlist_is_exactly_what_the_check_finds_on_the_real_tree`, `test_i_a_brand_rule_in_the_shared_scale_is_found`, `test_ii_gds_transport_as_a_font_face_under_the_pages_app_is_found`, and one more): **your change moves or removes GOV.UK rules the allowlist lists, so its entries are stale.** | **OPEN: this round.** |

## What you do (and nothing else)

1. **Take main in** (a merge, not a rebase). If the merge conflicts outside the allowlist file and its count, **STOP and tell the conductor.**
2. **Run PL12b's theme-rules test and `make -C OspreyFlow_Build design-check`** on the merged tree and **read which entries and which count they say are stale.**
3. **Lower the allowlist: delete the entries for the rules your change removed (a stale entry fails the check) and lower the recorded count by the same number: never raise it** (the file's own header says any slice that removes a rule may lower it). **No logic change of any kind: no code, no test, no fixture, no word of the sign-in chrome.** If a test fails for a reason other than a stale entry, **STOP and tell the conductor.**
4. **Say in your report:** the entries you deleted, the old and new count, and the results of the theme-rules test, `design-check` and your slice's checks.

**A finding that names a key, a credential, a certificate or a security rule is stopped and reported, never accepted narrower.**
