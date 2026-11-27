# SE9i: A Document keeps the legal basis it was uploaded under, stored with it, not only in the audit log

**Conduit part, with an amendment** (the owner's answers to the overnight drafts, 27 November 2026, after 09:40 UTC; RULINGS.md), from GG3e's question 5b. It is cut before RL2. GG3e's page does not wait for it.

## The finding (the overnight drafts' index)

The upload route takes `legal_basis` (`services/api/app.py`, about lines 7889 and 7993), but records it in the audit log only (about line 7941). The Document itself does not keep it.

## Round 1: the amendment diff first, then stop

Write `process/lanes/v062/SE9I_LEGAL_BASIS_AMENDMENT.diff`: the spec text, and the ADR amendment if one owns the Document's fields, saying that a Document stores the legal basis it was uploaded under, who may read it, and that it is never changed after upload. Run `git apply --check` against main. **Write no test and no code.** End with **"STOP: SE9i's amendment waits for the owner's approval."** The owner's approval and a clear-stop line start round 2.

## Round 2 (after the approval)

Store it, return it where the amendment says, and migrate nothing silently: say what an existing Document without one reads as.

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_document_legal_basis_stored.py` (new, pure; written in round 2, red on main).

## Out of scope

GG3e's page; any change to the audit row.
