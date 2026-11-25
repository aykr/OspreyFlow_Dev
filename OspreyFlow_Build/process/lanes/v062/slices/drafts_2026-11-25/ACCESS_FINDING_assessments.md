# An access finding: a case's gaps and assumptions name linked items with no visibility step (for the owner)

**Status: a finding from reading, not run, and not ruled.** Found on 25 November 2026 in the away round (D246) while
drafting the first GA1a (since withdrawn: GA1 is Ask & Chat). **It names an access rule (CLAUDE.md rules 3 and 4), so
it is the owner's.** Nothing was changed. The test below is the one I would write first. It was not run, and its red
is predicted from the code, not observed.

## What the code does (read at `4f77858a5`; re-read, lines move)

- **Judgements are hidden in full** from a reader who cannot see their `supporting` evidence (ADR-046):
  - `judgement_visible_to` is at `OspreyFlow_Core/services/api/assessments.py:491`;
  - `list_visible_judgements` (:535-555) is called by `GET .../judgements` (`services/api/app.py:7436`);
  - the save refuses a citation it cannot confirm (`_unverifiable_citations`, `assessments.py:430`);
  - the test is `OspreyFlow_Build/tests/services/api/test_assessment_routes.py:255-290`
    (`test_list_judgements_route_hides_one_with_an_unreadable_supporting_reference`: saved by a SECRET-cleared
    principal, listed by an OFFICIAL one, the list is `[]`).
- **Gaps are not.** An `IntelligenceGap` carries `linked_entities: list[NodeId]` (`packages/schemas/domain.py` about
  line 2074).
  - `save_gap_route` (`app.py:8770-8797`, `RECORD_ASSESSMENT`, editor level) stores the ids it is given with no check
    that they exist or that the saver may see them (`new_gap`, `assessments.py:614-626`).
  - `GapStore.list_for_investigation` (:360-370) selects by `investigation_id` and `owning_unit` only.
  - `list_gaps_route` (`app.py:8798-8812`, `INVESTIGATE`, viewer level) returns each gap whole, adding only the
    raiser's name.
- **Assumptions are not.** An `Assumption` carries `linked_judgements: list[JudgementId]` (about line 2086).
  - `save_assumption_route` (`app.py:8817-8845`) stores them unchecked (`new_assumption`, `assessments.py:637-647`).
  - `AssumptionStore.list_for_investigation` (:417-427) selects by case and unit only.
  - `GET .../assumptions` (:8846) returns them whole.
- **The existing tests cover neither case.** `test_save_and_list_gap_route` (:294) and
  `test_save_and_list_assumption_route` (:322) save with empty link lists and read as the same principal. Rule 4
  ("every read path gets an access-control test") is unmet for these two read paths' links.

## Why it may matter

Two readers of one case, with different clearance:
- **(1) A gap names a node the lower reader may not see.** The lower reader receives that node's id in
  `linked_entities`. They learn that a linked item exists, and how many there are. Rule 3 says an unauthorised
  principal "must not be able to detect a filtered node's existence".
- **(2) An assumption names a judgement hidden in full from the lower reader.** The lower reader receives the id of a
  judgement the judgements route never shows them. That defeats ADR-046's hide-in-full for the fact of its existence.
- **(3) On the write side,** anyone holding `RECORD_ASSESSMENT` can store any string as a linked id, unlike a
  judgement's citations. That is a weaker matter, but the same fix point.

Whether an internal id alone tells a reader anything is for the owner to judge. The Glass shows the gap's links today
(the React panel lists gaps with their status, `apps/workspace/src/assessment/JudgementsPanel.tsx:318`). How it shows
`linked_entities` was not read.

## The failing tests I would write first (red today, by reading)

In `OspreyFlow_Build/tests/services/api/test_assessment_routes.py`, beside the hide-in-full test, built the same way
(its `_write_investigation`, `_write_node` and `_bearer` helpers; the stores at their real Postgres, as that file
already does). The planted shape is the one the real routes receive and send (rule 15): a gap saved through
`POST .../gaps` by a SECRET-cleared editor, then listed through `GET .../gaps` by an OFFICIAL viewer of the same case.

```python
def test_a_gap_never_names_to_its_reader_a_node_they_may_not_see(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    visible_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit))
    hidden_id = asyncio.run(_write_node(owning_unit="unit-9", classification="SECRET"))
    secret_headers = _bearer(private_key, clearance="SECRET")
    official_headers = _bearer(private_key, clearance="OFFICIAL")

    from services.api.app import app

    with TestClient(app) as client:
        saved = client.post(
            f"/v1/investigations/{investigation_id}/gaps",
            headers=secret_headers,
            json={
                "investigation_id": investigation_id,
                "question": "Who supplied the vehicle?",
                "linked_entities": [visible_id, hidden_id],
                "status": "open",
            },
        )
        assert saved.status_code == 201, saved.text

        listed = client.get(f"/v1/investigations/{investigation_id}/gaps", headers=official_headers)
        assert listed.status_code == 200, listed.text
        # Whatever the owner rules (the hidden link dropped, or the gap hidden in full as a judgement
        # is), the lower reader's answer never contains the hidden node's id, anywhere in the body.
        assert hidden_id not in listed.text
        # And never a count that tells them one was removed.
        for gap in listed.json()["gaps"]:
            assert "linked_count" not in gap and "hidden" not in gap


def test_an_assumption_never_names_to_its_reader_a_judgement_hidden_from_them(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    visible_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit))
    hidden_id = asyncio.run(_write_node(owning_unit="unit-9", classification="SECRET"))
    secret_headers = _bearer(private_key, clearance="SECRET")
    official_headers = _bearer(private_key, clearance="OFFICIAL")

    from services.api.app import app

    with TestClient(app) as client:
        judgement = client.post(
            f"/v1/investigations/{investigation_id}/judgements",
            headers=secret_headers,
            json={
                "investigation_id": investigation_id,
                "statement": "Cites a SECRET node.",
                "probability_band": "likely",
                "supporting": [visible_id, hidden_id],
            },
        )
        assert judgement.status_code == 201, judgement.text
        hidden_judgement_id = judgement.json()["id"]
        # The precondition, from the existing test: the OFFICIAL reader is not shown this judgement.
        shown = client.get(f"/v1/investigations/{investigation_id}/judgements", headers=official_headers)
        assert shown.json()["judgements"] == []

        saved = client.post(
            f"/v1/investigations/{investigation_id}/assumptions",
            headers=secret_headers,
            json={
                "investigation_id": investigation_id,
                "statement": "The subject acted alone.",
                "if_false_impact": "The principal-organiser judgement falls over.",
                "linked_judgements": [hidden_judgement_id],
            },
        )
        assert saved.status_code == 201, saved.text

        listed = client.get(
            f"/v1/investigations/{investigation_id}/assumptions", headers=official_headers
        )
        assert listed.status_code == 200, listed.text
        assert hidden_judgement_id not in listed.text
```

**Why each is red today (by reading):** neither list route nor its store looks at what the ids point to, so the
hidden id is in the body as saved.

**How each is shown red for the right reason before the fix is believed (rule 15):** the precondition assertions (the
save returns 201, and the judgement is hidden from the lower reader) must pass, so a red cannot come from a refused
save or a missing fixture. A third case, `test_a_gap_names_to_its_reader_a_node_they_may_see`, keeps the visible id in
`linked_entities` for the OFFICIAL reader. It stops a "fix" that empties every list from passing.

**The write side, if the owner wants it:** `test_a_gap_cannot_link_a_node_its_saver_cannot_confirm`, modelled on
`test_save_judgement_route_rejects_an_unverifiable_citation_and_names_it` (:183), saving as the OFFICIAL editor with
the SECRET id: a refusal in words. Note the existing judgement rule: the refusal may name only an id the saver typed.

## Questions for the owner (the proposal first)

1. **Is it a fault?** (a) **Yes: an id the reader may not see is never sent** (rule 3). (b) No: ids alone tell nothing.
   Then the reason is recorded in the decision log and both tests are written to pin today's behaviour instead.
2. **The fix's shape, if (a).** (a) **A gap is shown with only the links the reader may see**: the hidden ones are
   dropped, with no count. **An assumption linking a judgement hidden from the reader is shown without that link.** An
   assumption is a person's own statement, not a claim resting on the hidden evidence. (b) Hide in full, as ADR-046
   does for judgements. That is stricter, but it hides a gap whose question the reader could otherwise work on.
3. **Where.** (a) **A small security part (an SE id), in the Conduit's two list routes, using the same visibility step
   as the judgements** (`GraphPort.get_node` under the reader's principal; `list_visible_judgements` for the
   assumptions' links), with the tests above written first. Never a filter in a page (rule 3). (b) Folded into a later
   assessment slice. Not proposed: a read path with an open access question should not wait for a page.
4. **The write side.** (a) **In the same part**: an unconfirmable linked id is refused in words, as a judgement's
   citation is. (b) Later.
