# SE9j: A site plan carries a marking, and a reader below it is never sent the site

**Security part, Conduit** (the owner's answers to the overnight drafts, 27 November 2026, after 09:40 UTC; RULINGS.md), from GG5e1's question 3. It is cut before RL2.

## The finding (GG5e1's draft)

A site plan (`/v1/investigations/{id}/sites…`, `services/api/app.py` from about line 10209) carries no marking, so every reader of the case is sent every site.

## Round 1: the amendment diff first, then stop

A marking on a new kind of record is a decision. Write `process/lanes/v062/SE9J_SITE_MARKING_AMENDMENT.diff`: the spec text, and the ADR amendment that owns markings on case records. It says that a site takes a marking at upload, up to the uploader's clearance; that a reader below it is sent no site, no count and no image, as the 404 a missing site gives (rules 3 and 4); and what existing sites read as. Run `git apply --check`. **Write no test and no code.** End with **"STOP: SE9j's amendment waits for the owner's approval."**

## Round 2 (after the approval)

Build it in the adapter or store's query, never by filtering after the read (rule 3). Write an access-control test for every site read path (rule 4).

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_site_marking.py` (new, pure; round 2, red on main). Store-backed cases go beside `test_sites_store.py` and are judged by the full gate.

## Out of scope

GG5e1's page; the sites list route, which is GG5e1's amendment (its question 2).
