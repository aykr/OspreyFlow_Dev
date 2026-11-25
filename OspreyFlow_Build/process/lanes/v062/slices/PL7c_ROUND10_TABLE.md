# PL7c: round 10, the one new rule (24 November 2026, 09:10 UTC; the conductor, on the owner's word)

**The owner's rule: no round from 5 on starts without a table of every open case.** One case is open; **every case of rounds 1 to 9 is closed except it** (the round-9 verifier named exactly this one).

| # | Case | Status |
| --- | --- | --- |
| 1 | **PL7c's identity switch adds one GOV.UK rule outside a theme folder: `[data-brand="govuk"][data-govuk-typeface="on"] { --ui: "GDS Transport", …; --govuk-typeface: …; }` in `OspreyFlow_Core/packages/design/tokens.css` (about line 204).** PL12b's ratchet (`OspreyFlow_Build/tests/fixtures/theme_rule_allowlist.txt`, `count: 70`, and `RATCHET_CEILING` in `OspreyFlow_Build/tools/theme_rule_check.py`) has no entry for it, so five of PL12b's tests fail on your tip (`test_the_real_tree_passes_with_the_allowlist`, `test_the_allowlist_is_exactly_what_the_check_finds_on_the_real_tree`, `test_i_a_brand_rule_in_the_shared_scale_is_found`, `test_ii_gds_transport_as_a_font_face_under_the_pages_app_is_found`, and every plant case that asserts a clean tree). | **OPEN: this round.** |

## The owner's ruling (24 November 2026, in chat): option A

**"PL7c: option A. My add-round line is in. Raise the allowlist count from 70 to 71 for the one new rule, citing my word and that the rule moves to the theme folder in PL12d. Nothing else changes."** The allowlist's own header says nobody may raise the count or add a line without the owner's word: **this is that word.**

## What you do (and nothing else)

1. **Add one entry to `theme_rule_allowlist.txt`** for exactly that rule, in the file's own format (path under `OspreyFlow_Core`, a tab, the key the check prints for it, a tab, the kind `rule`: **run `python -m tools.theme_rule_check --list` and copy the key it prints for the rule; do not hand-write it**), **and raise `count:` from 70 to 71 and `RATCHET_CEILING` in `tools/theme_rule_check.py` from 70 to 71** (the check fails if either disagrees with the file).
2. **Write one comment line in the allowlist's header** (above the entries, with the other notes) that says: **the count was raised from 70 to 71 on the owner's word of 24 November 2026 for PL7c's identity-switch rule `[data-brand="govuk"][data-govuk-typeface="on"]`, which moves to the GOV.UK theme folder in PL12d** (and the entry is then deleted and the count lowered as the header says).
3. **Find every test that pins the figure 70** (`git grep -n "70" -- OspreyFlow_Build/tests/glass_trees/test_theme_rules.py OspreyFlow_Build/tools/theme_rule_check.py` and the like) **and change only that figure and only where it is this count; say each in your report.**
4. **Nothing else: no logic change, no other file, no other rule.** Run `OspreyFlow_Build/tests/glass_trees/test_theme_rules.py`, `tools.design_check`, `tools.colour_drift_check`, the sign-in theme's node tests (`node --test OspreyFlow_Build/tests/keycloak_theme/*.test.mjs`) and your slice's checks, and say the results. **If anything fails for another reason, STOP and tell the conductor.**

**A finding that names a key, a credential, a certificate or a security rule is stopped and reported, never accepted narrower.**
