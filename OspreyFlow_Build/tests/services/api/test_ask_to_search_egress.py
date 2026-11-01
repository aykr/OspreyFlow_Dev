"""Ask to search carries the case's handling, so the analyst's engine choice applies (the owner's
answer of 1 November 2026; ADR-135 Amendment 1), under the same two gates as Ask the case: the
handling code (`models.sendable_handling_codes`) and each of the case's datasets' egress (ADR-136).

**What is sent, and under what.** The model is given the case's vocabulary and the analyst's question
about the case. It is sent under the handling the case's material shares *as the analyst sees it*
(`questions.shared_handling` over the visible working set: one handling code, or none), and as
coming from **every dataset of the case**, as Ask the case sends it. A case whose visible material
mixes handling codes, or that the analyst sees nothing of, has no shared handling and stays local.

The requests reach the stand-in gateway of `test_model_engines.py`, built from the renderer's own
model table; it refuses what the real LiteLLM proxy refuses (`CLAUDE.md` rule 15, shown again for
this table by `test_dataset_egress.py`). "Not sent" means it recorded no call for the hosted model.

What a mistake would do, and the case that catches it (rule 12):
- the choice still meaning nothing (no handling sent, the step 2 finding) —
  `test_a_case_whose_datasets_allow_it_is_sent_to_the_engine_chosen` (the positive control; red
  before this change, when the gateway was only ever asked for the local model);
- a dataset whose egress is `none` sent — `test_a_case_with_a_dataset_kept_in_is_never_sent`;
- the datasets read from what the analyst sees rather than the whole case, so a dataset the visible
  nodes do not come from is let out — `test_a_dataset_the_visible_nodes_do_not_come_from_still_keeps_the_case_in`
  (shown red with that very mistake planted);
- a handling code that may not leave sent — `test_a_case_of_mixed_handling_codes_stays_local`;
- a hidden node deciding where the question goes (rule 3) —
  `test_a_hidden_node_changes_nothing_about_where_it_goes`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from services.api import pattern_ask
from services.api.pattern_ask import PatternAskService
from services.api.working_set.service import WorkingSetService

from ontology.packs import load_deployment_ontology
from schemas.domain import Handling, Node, Principal, Subgraph
from schemas.model import ExtractionRequest, ExtractionResult
from tests.services.api.test_dataset_egress import GEMINI, LOCAL, STORE, _gateway, _routes
from tests.services.api.test_model_engines import StandInGateway

from .test_pattern_ask import CountingGraph, _two_visited
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, node

ONTOLOGY = load_deployment_ontology()
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


class _AnsweringGateway:
    """The stand-in gateway's own checks and record, answering with a proposal the Conduit can
    validate, so a request that reaches a model also comes back as a pattern."""

    def __init__(self, inner: StandInGateway) -> None:
        self.inner = inner

    @property
    def asked(self) -> list[str]:
        return self.inner.asked

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        await self.inner.extract(req)  # refuses as the real gateway does, and records the model
        return ExtractionResult(document_id=req.document_id, model=req.model, data=_two_visited())

    async def embed(self, texts: Sequence[str]) -> list[Any]:
        return []


class _CaseDatasets:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return self.ids if investigation_id == "inv-1" else []


def _held(node_id: str, *, code: str = "P", classification: str = "OFFICIAL",
          datasets: Sequence[str] = ("synthetic",)) -> Node:  # fmt: skip
    made = node(node_id, classification)
    handling = Handling(classification=classification, handling_code=code, originator="unit-1",
                        owning_unit="unit-1")  # fmt: skip
    return made.model_copy(update={"handling": handling, "datasets": list(datasets)})


async def _service(nodes: list[Node], case_datasets: list[str]) -> tuple[PatternAskService, Any]:
    from services.api.model_routing import RoutedModel

    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", nodes)
    gateway = _AnsweringGateway(_gateway())
    routed = RoutedModel(gateway, routes=_routes(), egress=STORE)  # type: ignore[arg-type]
    service = PatternAskService(
        WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME),
        CountingGraph(3),  # type: ignore[arg-type]
        routed,
        default_model=LOCAL,
        datasets=_CaseDatasets(case_datasets),
    )
    return service, gateway


async def _ask(service: PatternAskService, engine: str | None = "gemini") -> Any:
    return await service.ask(
        "inv-1",
        pattern_ask.AskToSearchRequest(question="Who visited whom?", engine=engine),
        ANALYST,
        ONTOLOGY,
    )


async def test_a_case_whose_datasets_allow_it_is_sent_to_the_engine_chosen() -> None:
    service, gateway = await _service([_held("p-1"), _held("p-2")], ["synthetic"])
    proposal = await _ask(service)
    assert gateway.asked == [GEMINI]
    assert (proposal.engine, proposal.model) == ("gemini", GEMINI)
    # And with no engine named, on the role's default (Gemini in this table).
    await _ask(service, engine=None)
    assert gateway.asked == [GEMINI, GEMINI]


async def test_a_case_with_a_dataset_kept_in_is_never_sent() -> None:
    service, gateway = await _service([_held("p-1", datasets=["kept-in"])], ["kept-in"])
    proposal = await _ask(service)
    assert GEMINI not in gateway.asked and gateway.asked == [LOCAL]
    assert proposal.engine == "local", "the answer says the local model answered"


async def test_a_dataset_the_visible_nodes_do_not_come_from_still_keeps_the_case_in() -> None:
    """The case holds two datasets, one kept in. Every node the analyst sees is from the other; the
    question is still about the whole case, so it stays local."""
    nodes = [_held("p-1"), _held("p-2"), _held("p-secret", classification="SECRET", datasets=["kept-in"])]
    service, gateway = await _service(nodes, ["synthetic", "kept-in"])
    proposal = await _ask(service)
    assert GEMINI not in gateway.asked
    assert proposal.engine == "local"


async def test_a_case_of_mixed_handling_codes_stays_local() -> None:
    nodes = [_held("p-1", code="P"), _held("p-2", code="C")]
    service, gateway = await _service(nodes, ["synthetic"])
    proposal = await _ask(service)
    assert gateway.asked == [LOCAL] and proposal.engine == "local"


async def test_a_case_the_analyst_sees_nothing_of_stays_local() -> None:
    service, gateway = await _service([], ["synthetic"])
    proposal = await _ask(service)
    assert gateway.asked == [LOCAL] and proposal.engine == "local"


async def test_a_hidden_node_changes_nothing_about_where_it_goes() -> None:
    """Rule 3: a node the analyst may not see, of another handling code, neither keeps the question
    in nor lets it out; where it goes is decided by what the analyst sees and the case's datasets."""
    seen = [_held("p-1"), _held("p-2")]
    hidden = _held("p-hidden", code="C", classification="SECRET")
    with_hidden, gateway_a = await _service([*seen, hidden], ["synthetic"])
    without, gateway_b = await _service(seen, ["synthetic"])
    await _ask(with_hidden)
    await _ask(without)
    assert gateway_a.asked == gateway_b.asked == [GEMINI]
