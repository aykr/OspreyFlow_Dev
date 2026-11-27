# SE9h: A case's access and datasets reads write an audit row, as every other case read does

**Security part, Conduit** (the owner's answers to the overnight drafts, 27 November 2026, after 09:40 UTC; RULINGS.md), from GR1f1's question 8. It is cut before RL2. GR1f1's page does not wait for it.

## The finding (the overnight drafts' index)

`GET /v1/investigations/{id}/access` (`services/api/app.py`, about line 4584) and `GET /v1/investigations/{id}/datasets` (about line 4334) write no audit row. Every other read of a case does.

## The rule

Each of the two reads writes one audit row, on success and on refusal alike, in the shape the case's other reads use: the same action vocabulary, the principal, the investigation's id, and no dataset or grantee detail beyond what those rows carry. Name the sibling read you copied.

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_case_access_reads_audited.py` (new, pure). Each route, on a granted read and on each refusal the route gives, writes exactly one row of the sibling's shape. **Red first:** the write removed at each route's real call site (rule 15).

## Out of scope

The link history, events and notes reads that the index also lists; those are a later part. Any page.
