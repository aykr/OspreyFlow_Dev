"""L3.5's red record, reproducible (rule 15): each plant breaks one rule at the call site its test
reaches, runs that test, and puts the file back. Run from `OspreyFlow_Core` with offline ports
pinned (for example `ARCADEDB_HTTP_PORT=2599 POSTGRES_PORT=55599 POSTGRES_PASSWORD=throwaway
VALKEY_PORT=6599 CLICKHOUSE_HTTP_PORT=18599`):

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_L3.5.py

Each row prints the plant, the tests run and pytest's tally; every plant must fail at least one.
The two live store plants (`--live`, under a lease) run against the leased Postgres.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

T = "../OspreyFlow_Build/tests/services/api/test_analyst_link_types.py"
S = "../OspreyFlow_Build/tests/services/api/test_link_type_service.py"
LS = "../OspreyFlow_Build/tests/services/api/test_link_type_store.py"
TS = "../OspreyFlow_Build/tests/services/api/test_target_models_store.py"
SVC = "services/api/link_types.py"
APP = "services/api/app.py"
STORE = "services/api/link_type_store.py"
MODELS = "services/api/target_models.py"
BOARDS = "services/api/boards.py"
TB = "../OspreyFlow_Build/tests/services/api/test_boards.py"

Plant = tuple[str, str, list[tuple[str, str]], list[str]]

OFFLINE: list[Plant] = [
    ("the promotable route answers every type as promotable", APP,
     [("PromotableType(name=name, promotable=reason is None, reason=reason)",
       "PromotableType(name=name, promotable=True, reason=None)")],
     [f"{T}::test_the_promotable_route_refuses_then_allows"]),
    ("the promotable route without the case's level", APP,
     [("    investigation: InvestigationViewerDep,\n    principal: PrincipalDep,\n    body: PromotableRequest,",
       "    investigation_id: str,\n    principal: PrincipalDep,\n    body: PromotableRequest,"),
      ("promotion_refusals(investigation.id, principal, body.types)",
       "promotion_refusals(investigation_id, principal, body.types)")],
     [f"{T}::test_a_stranger_to_the_case_is_told_the_promotable_check_does_not_exist"]),
    ("promotion_refusals ignores the proposal's status", SVC,
     [("                answers[name] = _why_not(name, own[-1].status)", "                answers[name] = None")],
     [f"{T}::test_a_proposed_types_links_are_refused_promotion_until_accepted_and_live"]),
    ("pending proposals offered in every case reading the dataset (ADR-099 Am 3's rule)", SVC,
     [("        pending = list(await self._store.pending_for_cases([investigation_id]))",
       ("        pending = list(await self._store.pending_for_cases([investigation_id]))\n"
        "        for d in _sources_of(principal):\n"
        "            pending += [p for p in await self._store.for_dataset(d) if p.status is ProposalStatus.PENDING]"))],
     [f"{T}::test_a_proposed_type_is_visible_only_in_its_own_case",
      f"{T}::test_a_proposed_type_is_visible_only_in_its_own_case_through_the_routes",
      f"{S}::test_a_proposal_is_offered_in_its_own_case_alone_not_every_case_of_its_dataset"]),
    ("withdrawal from any case reading the dataset", SVC,
     [("        in_reach = proposal.investigation_id == investigation_id",
       "        in_reach = proposal.dataset_id in (principal.datasets or []) or proposal.investigation_id == investigation_id")],
     [f"{T}::test_a_proposed_type_is_visible_only_in_its_own_case",
      f"{S}::test_the_proposer_withdraws_from_its_own_case_alone"]),
    ("the Model tab's list without the dataset's gate", APP,
     [("async def list_model_proposals(\n    dataset_id: StudioDatasetDep,",
       "async def list_model_proposals(\n    dataset_id: str,")],
     [f"{T}::test_the_model_tabs_proposals_are_the_datasets_alone_and_need_accept_types"]),
    ("a decision reads the proposal by id alone, not by its dataset", SVC,
     [("        proposal = await self._store.get_for_dataset(proposal_id, dataset_id)\n        if proposal.status is ProposalStatus.PENDING:",
       "        proposal = await self._store.get(proposal_id)\n        if proposal.status is ProposalStatus.PENDING:"),
      ("        proposal = await self._store.get_for_dataset(proposal_id, dataset_id)\n        decided =",
       "        proposal = await self._store.get(proposal_id)\n        decided =")],
     [f"{T}::test_another_datasets_proposal_is_not_found_on_this_datasets_tab"]),
    ("the proposer's own acceptance check removed", SVC,
     [("        if proposal.proposed_by == principal.id:\n            raise ProposalRefusedError(\n                \"You proposed",
       "        if False:\n            raise ProposalRefusedError(\n                \"You proposed")],
     [f"{T}::test_the_proposer_cannot_accept_their_own"]),
    ("the administrator decides a dataset's proposal", SVC,
     [("        if proposal.dataset_id is not None:\n            # ADR-090 Amendment 4",
       "        if False:\n            # ADR-090 Amendment 4")],
     [f"{T}::test_the_administrators_route_refuses_a_proposal_of_a_dataset"]),
    ("the administrator's promotion sweeps a dataset's proposal into the ontology", SVC,
     [("                    other.dataset_id is None\n                    and other.owning_unit",
       "                    True\n                    and other.owning_unit")],
     [f"{T}::test_the_administrators_promotion_never_merges_a_datasets_proposal"]),
    ("decline without its reason check", SVC,
     [("        good and keep reading as its name. Only from pending, by a write that checks it.\"\"\"\n        _check_reason(reason)",
       "        good and keep reading as its name. Only from pending, by a write that checks it.\"\"\"")],
     [f"{T}::test_a_declined_types_links_stay_in_the_layer_for_good"]),
    ("a name in the dataset's live model not refused at proposal", SVC,
     [("        if name in live:\n            raise ProposalRefusedError(",
       "        if False:\n            raise ProposalRefusedError(")],
     [f"{T}::test_a_name_already_in_the_datasets_live_model_is_refused_at_proposal"]),
    ("the proposal names the read set's last dataset (the layer)", SVC,
     [("        dataset_id = next(iter(_sources_of(principal)), None)\n        if principal.datasets is not None",
       "        dataset_id = (principal.datasets or [None])[-1]\n        if principal.datasets is not None")],
     [f"{T}::test_a_proposal_names_its_cases_source_dataset_never_its_layer"]),
    ("a case reading no dataset may propose", SVC,
     [("        if principal.datasets is not None and dataset_id is None:", "        if False:")],
     [f"{T}::test_a_case_reading_no_dataset_cannot_propose"]),
    ("an accepted type, once live, not offered in the dataset's other cases", SVC,
     [("        for accepted in await self._accepted_in_force(principal):\n            offered.setdefault(",
       "        for accepted in []:\n            offered.setdefault(")],
     [f"{T}::test_an_accepted_type_once_live_is_offered_in_every_case_of_its_dataset"]),
    ("no same-name merge at acceptance", SVC,
     [("                and other.status is ProposalStatus.PENDING\n                and _fits(other, accepted)",
       "                and False")],
     [f"{T}::test_accepting_merges_a_same_name_proposal_that_fits_and_leaves_one_that_does_not"]),
    ("the acceptance's claim not conditional on the status read", SVC,
     [("            direct_since=now if basis == \"direct\" else None,\n            only_from=proposal.status,",
       "            direct_since=now if basis == \"direct\" else None,\n            only_from=None,")],
     [f"{T}::test_an_acceptance_racing_a_decline_loses_and_writes_nothing"]),
    ("the claim not given back when the draft write is refused", SVC,
     [("        except BaseException:\n            await self._store.decide(",
       "        except BaseException:\n            raise\n            await self._store.decide(")],
     [f"{T}::test_a_refused_draft_write_gives_the_claim_back"]),
    ("an accepted type lost from the draft cannot be added again", SVC,
     [("        if proposal.status is ProposalStatus.ACCEPTED and proposal.name not in live | drafted:",
       "        if False:")],
     [f"{T}::test_an_accepted_type_lost_from_the_draft_is_said_and_may_be_added_again"]),
    ("a merged proposal no longer offered in its own case", SVC,
     [("            if p.status in _ACCEPTED_STATES and p.dataset_id is not None",
       "            if p.status is ProposalStatus.ACCEPTED and p.dataset_id is not None")],
     [f"{T}::test_a_merged_proposal_is_still_offered_in_its_own_case_before_live"]),
    ("the accepting data engineer's basis ignored", SVC,
     [("CaseType(definition=accepted.in_force(), storage_name=accepted.storage_name)",
       "CaseType(definition=accepted.definition(), storage_name=accepted.storage_name)")],
     [f"{T}::test_the_accepting_data_engineer_chooses_direct_and_it_holds_from_then"]),
]

OFFLINE += [
    ("a board lists hidden types (a proposal's storage label)", BOARDS,
     [("            if not e.system and not e.hidden and e.name not in _NOT_DRAWN_LINK_TYPES",
       "            if not e.system and e.name not in _NOT_DRAWN_LINK_TYPES")],
     [f"{TB}::test_a_board_neither_lists_nor_draws_under_a_proposals_storage_label",
      f"{T}::test_a_board_never_offers_a_proposals_storage_label"]),
    ("link's own hidden refusal removed and the list holding hidden types", BOARDS,
     [("            if not e.system and not e.hidden and e.name not in _NOT_DRAWN_LINK_TYPES",
       "            if not e.system and e.name not in _NOT_DRAWN_LINK_TYPES"),
      ("        if declared is not None and declared.hidden:", "        if False:")],
     [f"{TB}::test_a_link_is_never_drawn_under_a_proposals_storage_label"]),
]

LIVE: list[Plant] = [
    ("the old status check left in place", STORE,
     [(("ALTER TABLE link_type_proposals DROP CONSTRAINT IF EXISTS link_type_proposals_status_check;\n"
        "ALTER TABLE link_type_proposals ADD CONSTRAINT link_type_proposals_status_check CHECK (status IN\n"
        "    ('pending', 'promoted', 'rejected', 'withdrawn', 'merged', 'retired', 'accepted'));\n"), "")],
     [f"{LS}::test_a_table_made_before_accepted_takes_it_after_connect"]),
    ("the store's decision not conditional on the status read", STORE,
     [("\"WHERE id = $1 AND ($9::text IS NULL OR status = $9::text)\"", "\"WHERE id = $1 AND $9::text IS NOT DISTINCT FROM $9::text\"")],
     [f"{LS}::test_a_table_made_before_accepted_takes_it_after_connect"]),
    ("the dataset's model lock planted out of `_locked`", MODELS,
     [("            \"SELECT pg_advisory_xact_lock(hashtext('target_models:' || $1))\", dataset_id",
       "            \"SELECT 1 WHERE $1::text IS NOT NULL\", dataset_id")],
     [f"{TS}::test_two_link_types_added_at_once_both_land_in_the_draft"]),
]


def run(plants: list[Plant]) -> int:
    held = 0
    for title, file, swaps, tests in plants:
        path = pathlib.Path(file)
        before = path.read_text()
        after = before
        for old, new in swaps:
            assert after.count(old) == 1, f"{title}: the plant's text is not found once in {file}"
            after = after.replace(old, new)
        path.write_text(after)
        try:
            done = subprocess.run(
                [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
                 "no:warnings", "-p", "no:randomly", *tests],
                capture_output=True, text=True, check=False,
            )  # fmt: skip
        finally:
            path.write_text(before)
        tally = [line for line in done.stdout.splitlines() if " passed" in line or " failed" in line]
        red = done.returncode != 0
        held += 0 if red else 1
        names = ", ".join(t.split("::")[1] for t in tests)
        print(f"| {title} | `{file}` | {names} | {tally[-1].strip('= ') if tally else done.returncode} |")
    return held


if __name__ == "__main__":
    still_green = run(LIVE if "--live" in sys.argv else OFFLINE)
    sys.exit(1 if still_green else 0)
