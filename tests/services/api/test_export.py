"""`services/api/export.py` — `03_CONDUIT_MIDDLEWARE.md` §6, `02_GLASS_FRONTEND.md` §10, Phase 8
Against the accepted `06_DECISIONS.md` ADR-045/046/047. Real Postgres (the judgement
store, the export ledger, the investigations table) and real ArcadeDB (the handling-scheme gate,
the cross-session access recheck) — the same "a fake cannot stand in for this class of claim"
discipline every other test in this family already established.

`WorkingSetService` in these tests is built over a minimal, module-local `_MembershipOnlyStore`,
not `FakeWorkingSetStore` (a cross-directory import this file avoids) and not a real
`ValkeyWorkingSetStore` (this file needs no Valkey to prove the count's own arithmetic). The real
`GraphPort`/`HandlingScheme` already in scope in every test are passed through unchanged — only
the membership *storage* is a stand-in, the same "a fake stands in for storage, never for access
control" split `tests/services/api/working_set/test_service.py` already establishes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.assessments import JudgementStore, new_judgement
from services.api.config import PostgresConfig
from services.api.export import (
    ComplianceRoleRequiredError,
    ExportBlockedError,
    ExportItem,
    ExportLedgerStore,
    ExportRequest,
    OverrideRequiredError,
    export_manifest_policy_from_value,
    submit_export,
)
from services.api.investigations import InvestigationStore
from services.api.working_set.service import WorkingSetService

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

DSN = PostgresConfig.from_env().dsn

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
COMPLIANCE = Principal(
    id="compliance-1", clearance="OFFICIAL", org_unit="unit-9", roles=["compliance"]
)


@pytest.fixture
async def judgement_store():
    s = await JudgementStore.connect(DSN)
    yield s
    await s.close()


@pytest.fixture
async def ledger():
    s = await ExportLedgerStore.connect(DSN)
    yield s
    await s.close()


@pytest.fixture
async def investigations():
    s = await InvestigationStore.connect(DSN)
    yield s
    await s.close()


class _MembershipOnlyStore:
    """A minimal `WorkingSetStorage` stand-in for exactly the two methods
    `WorkingSetService.current_membership`/`withheld_count_for` read — this module's own tests
    never call `seed`/`expand`/etc. through the service, only its trusted read of a pre-populated
    membership, so nothing else is implemented."""

    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = {n.id: n for n in nodes}

    async def source_fidelity_nodes(self, investigation_id: str) -> dict[str, Node]:
        return dict(self._nodes)

    async def source_fidelity_edges(self, investigation_id: str) -> dict[str, object]:
        return {}


def _membership_node(*, owning_unit: str, classification: str = "OFFICIAL") -> Node:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Node(
        id=new_id(),
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="a" * 64)],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        audit=AuditStub(created_at=now, created_by="test"),
    )


def _working_set(graph, scheme, nodes: list[Node] | None = None) -> WorkingSetService:
    """A `WorkingSetService` whose membership store already contains `nodes` (default: none, so
    `withheld_count_for` returns 0) — every test below that doesn't care about the count's own
    value uses the default; the tests that do construct one with a real hidden node."""
    return WorkingSetService(graph, _MembershipOnlyStore(nodes or []), scheme)


def _node_write(
    *,
    owning_unit: str,
    classification: str = "OFFICIAL",
    handling_code: str = "P",
    sanitisation_code: str | None = None,
) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": "Exportfixture",
            "given_names": "E",
            "date_of_birth": "1990-01-01",
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code=handling_code,
            sanitisation_code=sanitisation_code,
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


def _base_request(items: list[ExportItem], **overrides) -> ExportRequest:
    kwargs = dict(
        artefact_kind="subgraph",
        items=items,
        resolution_threshold=0.95,
    )
    kwargs.update(overrides)
    return ExportRequest(**kwargs)


# --- 1. Every node/edge evaluated; a consult_originator item blocks AND is named ------------------


async def test_export_blocks_a_consult_originator_item_and_names_it(
    judgement_store, ledger
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (s2_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=ANALYST.org_unit, sanitisation_code="S2")], tx
        )
        await graph.commit_transaction(tx)

        handling = (await graph.get_node(s2_id, ANALYST)).handling
        item = ExportItem(id=s2_id, kind="node", handling=handling, label="the S2 record")
        request = _base_request([item])

        with pytest.raises(ExportBlockedError) as excinfo:
            await submit_export(
                investigation_id="inv-1",
                request=request,
                principal=ANALYST,
                graph=graph,
                scheme=scheme,
                judgements=judgement_store,
                ledger=ledger,
                working_set=working_set,
                manifest_policy="disclose",
            )
        assert len(excinfo.value.consult_originator) == 1
        assert excinfo.value.consult_originator[0].id == s2_id
        assert excinfo.value.consult_originator[0].label == "the S2 record"
        assert excinfo.value.consult_originator[0].reason == "consult_originator"


# --- 2. Override requires both a justification and an originator reference -----------------------


async def test_export_cannot_proceed_past_a_block_without_both_justification_and_originator(
    judgement_store, ledger
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (s2_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=ANALYST.org_unit, sanitisation_code="S2")], tx
        )
        await graph.commit_transaction(tx)
        handling = (await graph.get_node(s2_id, ANALYST)).handling
        item = ExportItem(id=s2_id, kind="node", handling=handling, label="the S2 record")

        # Neither.
        with pytest.raises(OverrideRequiredError):
            await submit_export(
                investigation_id="inv-1",
                request=_base_request([item]),
                principal=ANALYST,
                graph=graph,
                scheme=scheme,
                judgements=judgement_store,
                ledger=ledger,
                working_set=working_set,
                manifest_policy="disclose",
            )

        # Justification only.
        with pytest.raises(OverrideRequiredError):
            await submit_export(
                investigation_id="inv-1",
                request=_base_request([item], justification="cleared by supervisor"),
                principal=ANALYST,
                graph=graph,
                scheme=scheme,
                judgements=judgement_store,
                ledger=ledger,
                working_set=working_set,
                manifest_policy="disclose",
            )

        # Originator reference only.
        with pytest.raises(OverrideRequiredError):
            await submit_export(
                investigation_id="inv-1",
                request=_base_request([item], originator_reference="unit-1/ref-42"),
                principal=ANALYST,
                graph=graph,
                scheme=scheme,
                judgements=judgement_store,
                ledger=ledger,
                working_set=working_set,
                manifest_policy="disclose",
            )

        # Both — proceeds.
        result = await submit_export(
            investigation_id="inv-1",
            request=_base_request(
                [item], justification="cleared by supervisor", originator_reference="unit-1/ref-42"
            ),
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )
        assert result.mark.investigation_id == "inv-1"


# --- 3. The manifest policy fails closed to disclose, not the reverse ----------------------------


def test_export_manifest_policy_defaults_to_disclose_when_unset_empty_or_unrecognised() -> None:
    assert export_manifest_policy_from_value(None) == "disclose"
    assert export_manifest_policy_from_value("") == "disclose"
    assert export_manifest_policy_from_value("bogus") == "disclose"
    assert export_manifest_policy_from_value("DISCLOSE") == "disclose"  # not a case-insensitive
    # match to "omit" either — the whitelist is exact, per ADR-045's own fail-closed text.
    assert export_manifest_policy_from_value("omit") == "omit"


async def test_export_manifest_omitted_from_payload_under_omit_policy(
    judgement_store, ledger
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        # A real hidden item in the working set's own membership — SECRET, invisible to ANALYST —
        # so this test's own `disclose`/`omit` assertion is against a real, non-trivial count, not
        # the vacuous zero an empty working set would give either policy alike.
        visible = _membership_node(owning_unit=ANALYST.org_unit)
        hidden = _membership_node(owning_unit="unit-9", classification="SECRET")
        working_set = _working_set(graph, scheme, [visible, hidden])

        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        await graph.commit_transaction(tx)
        handling = (await graph.get_node(node_id, ANALYST)).handling
        item = ExportItem(id=node_id, kind="node", handling=handling)

        disclosed = await submit_export(
            investigation_id="inv-1",
            request=_base_request([item]),
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )
        assert disclosed.manifest.withheld_count == 1

        omitted = await submit_export(
            investigation_id="inv-1",
            request=_base_request([item]),
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="omit",
        )
        assert omitted.manifest.withheld_count is None


async def test_a_client_cannot_influence_the_withheld_count_in_the_artefact(
    judgement_store, ledger
) -> None:
    """The defect this test exists to catch: a caller-supplied count would let an artefact state
    that nothing was withheld when items were — an active misstatement of completeness, worse than
    the omission ADR-045 exists to prevent. `ExportRequest` carries no `withheld_count` field at
    all — a JSON body claiming one is silently ignored by Pydantic, not merely overridden — so a
    client attempting `withheld_count=0` against a working set that genuinely hides one item still
    gets the true, non-zero figure back."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        visible = _membership_node(owning_unit=ANALYST.org_unit)
        hidden = _membership_node(owning_unit="unit-9", classification="SECRET")
        working_set = _working_set(graph, scheme, [visible, hidden])

        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        await graph.commit_transaction(tx)
        handling = (await graph.get_node(node_id, ANALYST)).handling
        item = ExportItem(id=node_id, kind="node", handling=handling)

        # A raw dict, as an HTTP client's own JSON body would arrive, claiming zero withheld —
        # Pydantic drops the unknown field rather than raising, which is itself the point: there
        # is no field left for a client to lie through.
        request = ExportRequest(**{**_base_request([item]).model_dump(), "withheld_count": 0})
        assert not hasattr(request, "withheld_count")

        result = await submit_export(
            investigation_id="inv-1",
            request=request,
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )
        assert result.manifest.withheld_count == 1


# --- 4. ADR-046's export rule: judgement citations re-verified against the exporter's own access -


async def test_export_verifies_judgement_citations_against_the_exporting_analysts_own_access(
    judgement_store, ledger
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (visible_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        (secret_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit="unit-9", classification="SECRET")], tx
        )
        await graph.commit_transaction(tx)

        secret_cleared_author = Principal(id="author-1", clearance="SECRET", org_unit="unit-1")
        j = new_judgement(
            investigation_id="inv-1",
            statement="The subject is the principal organiser.",
            probability_band="likely",
            supporting=[visible_id, secret_id],
            author=secret_cleared_author.id,
        )
        await judgement_store.save(j, secret_cleared_author, graph)

        selection_item_handling = (await graph.get_node(visible_id, ANALYST)).handling
        item = ExportItem(id=visible_id, kind="node", handling=selection_item_handling)

        # ANALYST (OFFICIAL) is exporting — cannot see the SECRET citation, even though the
        # judgement itself was saved by someone who could.
        with pytest.raises(ExportBlockedError) as excinfo:
            await submit_export(
                investigation_id="inv-1",
                request=_base_request([item], judgement_ids=[j.id]),
                principal=ANALYST,
                graph=graph,
                scheme=scheme,
                judgements=judgement_store,
                ledger=ledger,
                working_set=working_set,
                manifest_policy="disclose",
            )
        assert len(excinfo.value.citation_unverifiable) == 1
        assert excinfo.value.citation_unverifiable[0].id == j.id
        assert excinfo.value.citation_unverifiable[0].reason == "citation_unverifiable"

        # The SECRET-cleared exporter, exporting the same judgement, succeeds.
        result = await submit_export(
            investigation_id="inv-1",
            request=_base_request([item], judgement_ids=[j.id]),
            principal=secret_cleared_author,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )
        assert result.ledger_entry_id


# --- 5. ADR-047's mark: highest handling level, and the pipeline can never omit it ----------------


async def test_export_mark_encodes_the_highest_handling_level_present(
    judgement_store, ledger
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    # A principal cleared for the higher of the two levels in this selection — this test's own
    # point is the mark's own mixed-handling computation, not the access gate (already covered by
    # its own dedicated tests above/below).
    sensitive_cleared = Principal(
        id="exporter-1", clearance="OFFICIAL-SENSITIVE", org_unit=ANALYST.org_unit
    )
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (official_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        (sensitive_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=ANALYST.org_unit, classification="OFFICIAL-SENSITIVE")], tx
        )
        await graph.commit_transaction(tx)

        items = [
            ExportItem(
                id=official_id,
                kind="node",
                handling=(await graph.get_node(official_id, sensitive_cleared)).handling,
            ),
            ExportItem(
                id=sensitive_id,
                kind="node",
                handling=(await graph.get_node(sensitive_id, sensitive_cleared)).handling,
            ),
        ]
        result = await submit_export(
            investigation_id="inv-1",
            request=_base_request(items),
            principal=sensitive_cleared,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )
        assert result.mark.handling_level == "OFFICIAL-SENSITIVE"
        assert result.mark.osprey_mark == "OspreyFlow"


async def test_the_export_pipeline_never_produces_an_artefact_with_no_mark(
    judgement_store, ledger
) -> None:
    """`ExportResult.mark` is a required Pydantic field — verified non-vacuous by attempting to
    construct the model without one, the type-level proof that the pipeline cannot silently skip
    it, alongside the behavioural proof (a real `submit_export` call always returns one)."""
    from pydantic import ValidationError
    from services.api.export import ExportManifest, ExportResult

    with pytest.raises(ValidationError):
        ExportResult(  # type: ignore[call-arg]
            manifest=ExportManifest(policy="disclose", withheld_count=0), ledger_entry_id="x"
        )

    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        await graph.commit_transaction(tx)
        handling = (await graph.get_node(node_id, ANALYST)).handling
        item = ExportItem(id=node_id, kind="node", handling=handling)
        result = await submit_export(
            investigation_id="inv-1",
            request=_base_request([item]),
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )
        assert result.mark is not None


# --- 6/7. The compliance-facing export ledger -----------------------------------------------------


async def test_export_ledger_entry_survives_investigation_deletion(
    judgement_store, ledger, investigations
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        investigation = await investigations.create(ANALYST)

        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        await graph.commit_transaction(tx)
        handling = (await graph.get_node(node_id, ANALYST)).handling
        item = ExportItem(id=node_id, kind="node", handling=handling)

        result = await submit_export(
            investigation_id=investigation.id,
            request=_base_request([item]),
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )

        # The investigation row is deleted directly — InvestigationStore exposes no delete
        # method at all today, deliberately (no route in this build ever deletes one); this is
        # the structural proof the ledger has no foreign-key or ownership dependency on it.
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute("DELETE FROM investigations WHERE id = $1", investigation.id)
        finally:
            await conn.close()

        with pytest.raises(Exception):
            await investigations.get(investigation.id)

        entries = await ledger.list_all(COMPLIANCE)
        assert any(e.id == result.ledger_entry_id for e in entries)


async def test_a_compliance_principal_can_list_every_export_without_investigation_access(
    judgement_store, ledger
) -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        await graph.commit_transaction(tx)
        handling = (await graph.get_node(node_id, ANALYST)).handling
        item = ExportItem(id=node_id, kind="node", handling=handling)

        await submit_export(
            investigation_id="inv-compliance-test",
            request=_base_request([item]),
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )

        entries = await ledger.list_all(COMPLIANCE)
        assert any(e.investigation_id == "inv-compliance-test" for e in entries)

        with pytest.raises(ComplianceRoleRequiredError):
            await ledger.list_all(ANALYST)


async def test_export_ledger_entry_carries_no_item_names_or_justification_content(
    judgement_store, ledger
) -> None:
    """`ExportLedgerEntry` is metadata only — who, when, which investigation, which handling
    level, whether a justification and originator reference were *given*, never their content and
    never an item's own name. A `consult_originator` override here supplies a justification and
    originator reference that each name the withheld item and its subject by a distinctive string;
    this test fails if either string ever reaches a compliance principal's own read of the ledger,
    proving the fix rather than only asserting the field is a `bool` by type."""
    secret_marker = "Distinctive-Justification-Marker-Naming-The-Item-Xk9q"
    originator_marker = "Distinctive-Originator-Reference-Marker-Zt3v"

    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (s2_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=ANALYST.org_unit, sanitisation_code="S2")], tx
        )
        await graph.commit_transaction(tx)
        handling = (await graph.get_node(s2_id, ANALYST)).handling
        item = ExportItem(id=s2_id, kind="node", handling=handling, label="the S2 record")

        result = await submit_export(
            investigation_id="inv-ledger-content-test",
            request=_base_request(
                [item], justification=secret_marker, originator_reference=originator_marker
            ),
            principal=ANALYST,
            graph=graph,
            scheme=scheme,
            judgements=judgement_store,
            ledger=ledger,
            working_set=working_set,
            manifest_policy="disclose",
        )

        entries = await ledger.list_all(COMPLIANCE)
        entry = next(e for e in entries if e.id == result.ledger_entry_id)

        assert entry.justification_given is True
        assert entry.originator_reference_given is True
        assert not hasattr(entry, "justification")
        assert not hasattr(entry, "originator_reference")
        serialised = entry.model_dump_json()
        assert secret_marker not in serialised
        assert originator_marker not in serialised
        assert s2_id not in serialised
        assert "the S2 record" not in serialised


# --- 8. Cross-session access: the export re-checks fresh, not the in-session snapshot -------------


async def test_export_is_refused_when_an_item_becomes_inaccessible_between_selection_and_export(
    judgement_store, ledger
) -> None:
    """The in-session Glass view and the export-time evaluation are two separate reads. A node the
    exporting analyst could see when they built their selection, and has since been reclassified
    (a real, live `supersede_node`, not a stale in-memory flag), is refused and named at export
    time — the export gate never trusts the client's own submitted handling for a node, only what
    `graph.get_node` says *now*."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        working_set = _working_set(graph, scheme)
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_node_write(owning_unit=ANALYST.org_unit)], tx)
        await graph.commit_transaction(tx)

        # The analyst builds their selection while the node is still OFFICIAL/unit-1 — visible.
        in_session_handling = (await graph.get_node(node_id, ANALYST)).handling
        item = ExportItem(
            id=node_id, kind="node", handling=in_session_handling, label="Endpoint fixture"
        )

        # Access changes: the node is reclassified SECRET/unit-9 since the selection was built —
        # a real supersede, not a stale client flag.
        tx = await graph.begin_transaction()
        reclassified = _node_write(owning_unit="unit-9", classification="SECRET")
        await graph.supersede_node(node_id, reclassified, tx)
        await graph.commit_transaction(tx)

        with pytest.raises(ExportBlockedError) as excinfo:
            await submit_export(
                investigation_id="inv-1",
                request=_base_request([item]),
                principal=ANALYST,
                graph=graph,
                scheme=scheme,
                judgements=judgement_store,
                ledger=ledger,
                working_set=working_set,
                manifest_policy="disclose",
            )
        assert len(excinfo.value.access_denied) == 1
        assert excinfo.value.access_denied[0].id == node_id
        assert excinfo.value.access_denied[0].label == "Endpoint fixture"
        assert excinfo.value.access_denied[0].reason == "access_denied"
