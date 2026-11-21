"""SE8a: every model call is recorded with who asked, for which case, and which engine and model
answered (`RULINGS.md` SE8: "every model call recorded with who asked, for which case and to which
engine, in one record"; rules 3, 4, 12 and 15). Names only: never a prompt, an answer, a document's
text, a key, a token or an engine's address.

**The record.** One `audit_log` row per model call, action `model_call`, written by the route that
asked (the person, the case) beside the access row it already writes. Its `resolved_query` holds
exactly `job` (ask, extract, email, transcribe, describe, embed, pattern_ask), `engine`, `model`
(both from the routing's own decision for the call, `RoutedModel.choose`: the engine registry's
record of the target, not the request body; null for a call refused before any engine was chosen),
`outcome` (answered, refused, errored, interrupted) and `via` (the action of the route's own row).

**What this proves, and how each claim fails (rule 15).** Each path is run through the real route,
the real service (the fakes the service tests keep), the real `RoutedModel` and the real
`AuditWriter` over a pool that captures every column it inserts. Its planted faults are made at the
shape the code sees: the attribution removed at the route's own site, the engine taken from the
request body instead of the routing's choice, a prompt, an address and a key written into the
record by the code that builds it, an error's own text written as a reason.

**The two scans** (rule 12: "which test fails if a new caller of the model port exists?"):

- `test_every_model_port_caller_is_one_the_list_names` finds a call by its method (`extract`,
  `transcribe`, `describe_image`, `embed`) on **any** object, and a file by its importing the port,
  its gateway adapter, Laurium's or the routing wrapper (`model_routing`, however imported). It
  walks, for calls,
  **`OspreyFlow_Core/services` (every subfolder), `scripts`, `harness`, `cli` and `connectors`**,
  and, for files that import the model port, its gateway adapter or Laurium's, the same folders and
  **`OspreyFlow_Core/packages`** (all but the adapters that implement the port and the schemas and
  ports that declare it). A caller not in `REVIEWED_CALLERS` / `REVIEWED_FILES`, and an entry whose
  caller has gone, both fail.
- `test_every_chain_that_reaches_a_model_is_asked_inside_an_attribution` follows the model on from
  the port: a function that reaches it (a port method, `run_extraction` by the module it is
  imported from, a method of a service on a receiver declared or built as that service, through
  the routes' `QuestionsDep`-style aliases and `request.app.state`) is itself followed, to a fixed
  point. A function nothing refers to that reaches the model is a **root**, and must not exist: a
  route asks inside `model_calls.attributed(…)` (which ends the chain), or the root is named in
  `REVIEWED_ROOTS` with its reason. It walks **`OspreyFlow_Core/services` (every subfolder),
  `scripts`, `harness`, `cli` and `connectors`**. Planted, at the shape a real change takes: a new
  service importing `run_extraction`, a chain of two new callers, a function handed over without
  being called, a route holding the service under another name or off the app's state, and each
  route's own attribution removed. What it does not follow is written in `reach_of`'s docstring
  (a service passed untyped through a helper, `getattr`): the first scan is what finds those.

Pure: no store, no network. The live stack owes: the gateway's own call
(`test_model_gateway_live.py` is the existing live case) and a real Postgres insert of the row (the
writer is the existing one, its insert proven by `test_audit_*` against Postgres).
"""

from __future__ import annotations

import ast
import asyncio
import functools
import json
import pathlib
import secrets
import shutil
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_case_views,
    get_document_content,
    get_email_extraction,
    get_extraction_candidates,
    get_investigations,
    get_model,
    get_ontology,
    get_pattern_ask,
    get_principal,
    get_principal_names,
    get_questions,
    get_search_index,
    get_search_working_set,
    get_valkey,
    get_working_set,
)
from services.api.audit import AuditWriter
from services.api.investigations import (
    AccessLevel,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.model_routing import Engine, ModelRoutes, RoutedModel

from adapters.model_litellm.errors import (
    ExtractionFailedError,
    InvalidExtractionSchemaError,
    ModelEngineRefused,
    ModelLimitReached,
    ModelUnavailableError,
    TranscriptionFailedError,
)
from schemas.domain import Principal
from schemas.model import (
    ExtractionRequest,
    ExtractionResult,
    ImageAnalysis,
    TranscribeRequest,
    Transcript,
    TranscriptSegment,
    VisionRequest,
)

from .test_document_content import _service as _document_service
from .test_email_extraction import HANDLING, ONTOLOGY, InMemoryCandidates
from .test_email_extraction import _build as _email_service
from .test_pattern_ask import ONTOLOGY as PATTERN_ONTOLOGY
from .test_pattern_ask import _case as _pattern_service
from .test_pattern_ask import _two_visited
from .test_questions import ANSWER
from .test_questions import _service as _questions_service

CORE = pathlib.Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
SERVICES = CORE / "services"
APP = SERVICES / "api" / "app.py"

#: Synthetic, made at run time, and put where a careless record could reach them: the prompt in the
#: question and the model's echo of it, the address and the key in the text of the errors a
#: transport raises and on the stand-in engine itself (rule 9; the brief's item 3).
KEY = "sk-" + secrets.token_hex(16)
PROMPT = "what-did-" + secrets.token_hex(8)
ADDRESS = f"http://engine-{secrets.token_hex(6)}.internal:4000"
#: A dataset's name: the egress refusal's words name datasets (`dataset_refusal`), and no audit
#: column may carry them.
DATASET = "dataset-" + secrets.token_hex(6)
SECRETS = {"key": KEY, "prompt": PROMPT, "address": ADDRESS, "dataset": DATASET}

ACTING = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
STRANGER = Principal(id="eve", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])
CASE = "inv-1"
BASE = f"/v1/investigations/{CASE}"

LOCAL_MODELS = {
    "extraction": "qwen-local",
    "vision": "vision-local",
    "transcription": "speech-local",
    "embedding": "embed-local",
}


# --- the stand-in for the audit store: every column the real writer inserts ---------------------


class _Conn:
    def __init__(self, pool: _Pool) -> None:
        self._pool = pool

    async def execute(self, sql: str, *args: Any) -> None:
        assert sql.lstrip().startswith("INSERT INTO audit_log"), sql
        if args[2] in self._pool.down_for:
            raise OSError("the audit store is down")
        self._pool.rows.append(
            dict(
                zip(
                    (
                        "recorded_at",
                        "principal_id",
                        "action",
                        "investigation_id",
                        "resolved_query",
                        "result_cardinality",
                        "justification",
                        "org_unit",
                    ),  # fmt: skip
                    args,
                    strict=True,
                )
            )
        )


class _Pool:
    """What `AuditWriter` asks of a pool; refuses an insert of an action in `down_for`."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.down_for: set[str] = set()

    @asynccontextmanager
    async def acquire(self) -> Any:
        yield _Conn(self)


def _calls(pool: _Pool) -> list[dict[str, Any]]:
    """Each `model_call` row's `resolved_query`, after checking every other column of it."""
    out = []
    for row in pool.rows:
        if row["action"] != "model_call":
            continue
        assert row["principal_id"] == ACTING.id
        assert row["investigation_id"] == CASE
        assert row["org_unit"] == ACTING.org_unit
        assert row["justification"] is None
        out.append(json.loads(row["resolved_query"]))
    return out


def _leaks(pool: _Pool) -> list[str]:
    """Which synthetic values appear in any column of any row."""
    found = []
    for row in pool.rows:
        text = " ".join(str(v) for v in row.values())
        found += [f"{name} in {row['action']}" for name, value in SECRETS.items() if value in text]
    return found


# --- the stand-in for the model: it refuses what the real one refuses (rule 15) -----------------


class _Inner:
    """A `ModelPort` as the adapter behind the routing is. It answers, and it also raises the port's
    real errors (`failure`), with the text a transport's error carries: the engine's address and the
    key the call used. It can hang until cancelled (`hang`). It holds a key and an address, as the
    gateway client does."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.api_key = KEY
        self.base_url = ADDRESS
        self.failure: Exception | None = None
        self.hang = False
        self.started = asyncio.Event()
        self.calls = 0

    async def _go(self) -> None:
        self.calls += 1
        self.started.set()
        if self.hang:
            await asyncio.Event().wait()
        if self.failure is not None:
            raise self.failure

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        await self._go()
        return ExtractionResult(document_id=req.document_id, model=req.model, data=self.data)

    async def describe_image(self, req: VisionRequest) -> ImageAnalysis:
        await self._go()
        return ImageAnalysis(
            document_id=req.document_id,
            model=req.model,
            data={"description": f"Tomasz WOLSKI, who asked {PROMPT}", "visible_text": ""},
        )

    async def transcribe(self, req: TranscribeRequest) -> Transcript:
        await self._go()
        return Transcript(
            document_id=req.document_id,
            model=req.model,
            language="en",
            segments=[TranscriptSegment(start=0, end=2, text=f"Tomasz is driving {PROMPT}.")],
        )

    async def embed(self, texts: Any) -> list[list[float]]:
        await self._go()
        return [[0.0] for _ in texts]


def _leaky(kind: type[Exception] = ExtractionFailedError) -> Exception:
    return kind(f"POST {ADDRESS}/v1/chat/completions failed (key {KEY}) for {PROMPT}")


#: What the real port raises, as the routing gets it, and how it is told apart (the outcome).
FAILURES: dict[str, tuple[str, Any]] = {
    "extraction failed": ("errored", lambda: _leaky()),
    "model not yet pulled": ("errored", lambda: _leaky(ModelUnavailableError)),
    "malformed schema": ("errored", lambda: _leaky(InvalidExtractionSchemaError)),
    "transcription failed": ("errored", lambda: _leaky(TranscriptionFailedError)),
    "a limit set in Admin › Models": ("refused", lambda: ModelLimitReached("requests")),
    "the provider refused": ("refused", lambda: ModelEngineRefused("key")),
}


def _routes(*, hosted_default: bool = False, no_local: bool = False) -> ModelRoutes:
    gemini = Engine(
        name="gemini",
        label="Gemini",
        models={"extraction": "gemini/flash"},
        key_present=True,
        privacy_contract=True,
    )
    locals_ = {**LOCAL_MODELS, **({"extraction": None} if no_local else {})}
    return ModelRoutes(
        locals=locals_,  # type: ignore[arg-type]
        engines={"gemini": gemini},
        defaults={"extraction": "gemini"} if hosted_default else {},
        sendable=frozenset({"P"}) if hosted_default else frozenset(),
    )


class _AnyDatasetMayGo:
    """ADR-136: every dataset allows a hosted engine (`egress` says otherwise: `none` or
    `contracted`, which the stand-in engine, under a contract, would accept)."""

    def __init__(self, egress: str = "any") -> None:
        self.egress = egress

    async def egress_of(self, ids: Any) -> dict[str, Any]:
        from datetime import UTC, datetime

        from services.api.datasets import Dataset

        return {
            i: Dataset(
                id=i, name=DATASET, owning_unit="unit-1",
                created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="x",
                egress=self.egress,  # type: ignore[arg-type]
            )
            for i in ids
        }  # fmt: skip


class _OneCase:
    """The case store of `inv-1`, which only unit-1 can see; any other unit, and any other case
    id, is not found, with the same error."""

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        from datetime import UTC, datetime

        if investigation_id != CASE or principal.org_unit != "unit-1":
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(
            id=CASE,
            name="A case",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="analyst-1",
            owning_unit="unit-1",
        )

    async def get(self, investigation_id: str) -> Investigation:
        raise AssertionError("not asked")


class _Names:
    async def display_names(self, ids: Any) -> dict[str, str]:
        return {}


class _Valkey:
    async def publish(self, channel: str, message: str) -> int:
        return 0


# --- the five paths, each wired as the app wires it ---------------------------------------------


@dataclass
class Scenario:
    name: str
    url: str
    via: str
    body: Any  # () -> dict
    jobs: list[tuple[str, str]]  # (job, role) of each call, in order, when all answer
    data: Any  # () -> the model's answer


def _body_ask() -> dict[str, Any]:
    return {"question": f"Who owns it? {PROMPT}"}


PATHS: dict[str, Scenario] = {
    p.name: p
    for p in (
        Scenario("ask", f"{BASE}/questions", "ask_question", _body_ask, [("ask", "extraction")],
             lambda: {**ANSWER, "answer": f"{ANSWER['answer']} {PROMPT}", "entities": []}),
        Scenario("run_extraction", f"{BASE}/ingest/extract", "run_extraction",
             lambda: {"document_id": "doc-1", "text": f"Statement of: Dana MERCER. {PROMPT}",
                      "profile": {"entity_types": ["Person"]},
                      "handling": HANDLING.model_dump(), "model": "caller-named-model"},
             [("extract", "extraction")],
             lambda: {"Person": [{"family_name": "MERCER", "confidence": 0.9}]}),
        Scenario("email", f"{BASE}/links/e1/events/ev-1/extract", "extract_email",
             lambda: {"using": "model", "model": "caller-named-model"},
             [("email", "extraction")],
             lambda: {"Person": [{"family_name": "MERCER", "confidence": 0.9}]}),
        Scenario("document_image", f"{BASE}/documents/image-1/extract", "extract_document",
             lambda: {"using": "model"},
             [("describe", "vision"), ("extract", "extraction")],
             lambda: {"Person": [{"family_name": "WOLSKI", "confidence": 0.8}]}),
        Scenario("document_video", f"{BASE}/documents/video-1/extract", "extract_document",
             lambda: {"using": "model"},
             [("transcribe", "transcription"), ("extract", "extraction")],
             lambda: {"Person": [{"family_name": "WOLSKI", "confidence": 0.8}]}),
        Scenario("pattern_ask", f"{BASE}/patterns/ask", "patterns_ask",
             lambda: {"question": f"Who visited whom? {PROMPT}"}, [("pattern_ask", "extraction")],
             lambda: _two_visited()),
    )
}  # fmt: skip


class Run:
    """One path, wired through the real route, service, `RoutedModel` and `AuditWriter`."""

    def __init__(
        self,
        path: Scenario,
        *,
        hosted: bool = False,
        principal: Principal = ACTING,
        egress: str = "any",
        no_local: bool = False,
    ) -> None:
        self.path = path
        self.pool = _Pool()
        self.inner = _Inner(path.data())
        self.routed = RoutedModel(
            self.inner,  # type: ignore[arg-type]
            routes=_routes(hosted_default=hosted, no_local=no_local),
            egress=_AnyDatasetMayGo(egress) if hosted else None,
        )
        # Extraction reads the datasets from the principal's scope; the other paths from the case.
        self.principal = (
            principal.model_copy(update={"datasets": ["ds-1"]})
            if hosted and path.name == "run_extraction"
            else principal
        )
        overrides: dict[Any, Any] = {
            get_principal: lambda: self.principal,
            get_audit: lambda: AuditWriter(self.pool),  # type: ignore[arg-type]
            get_investigations: lambda: _OneCase(),
            get_valkey: lambda: _Valkey(),
        }
        name = path.name
        if name == "ask":
            service = asyncio.run(_questions_service())[0]
            if hosted:
                from datetime import UTC, datetime

                from services.api.datasets import Dataset

                # The case reads one dataset, named as the egress refusal's words name it.
                store = service._datasets
                store.add(  # type: ignore[attr-defined]
                    Dataset(
                        id="ds-1",
                        name=DATASET,
                        owning_unit="unit-1",
                        egress=egress,  # type: ignore[arg-type]
                        created_at=datetime(2026, 1, 1, tzinfo=UTC),
                        created_by="x",
                    )  # fmt: skip
                )
                store.cases[CASE] = ["ds-1"]  # type: ignore[attr-defined]
                self.routed = RoutedModel(
                    self.inner,  # type: ignore[arg-type]
                    routes=_routes(hosted_default=True, no_local=no_local),
                    egress=store,
                )
            service._model = self.routed
            overrides |= {
                get_questions: lambda: service,
                get_principal_names: lambda: _Names(),
                get_case_views: lambda: None,
                get_working_set: lambda: None,
                get_search_index: lambda: None,
                get_search_working_set: lambda: None,
            }
        elif name == "run_extraction":
            overrides |= {
                get_model: lambda: self.routed,
                get_extraction_candidates: lambda: InMemoryCandidates(),
                get_ontology: lambda: ONTOLOGY,
            }
        elif name == "email":
            email = asyncio.run(_email_service())[0]
            email._model = self.routed
            overrides[get_email_extraction] = lambda: email
        elif name.startswith("document"):
            document = asyncio.run(_document_service())[0]
            document._model = self.routed
            overrides[get_document_content] = lambda: document
        else:
            pattern = asyncio.run(_pattern_service(path.data()))[0]
            pattern._proposer._model = self.routed
            overrides |= {get_pattern_ask: lambda: pattern, get_ontology: lambda: PATTERN_ONTOLOGY}
        app.dependency_overrides.update(overrides)
        self.client = TestClient(app, raise_server_exceptions=False)

    def post(self, **extra: Any) -> Any:
        return self.client.post(self.path.url, json={**self.path.body(), **extra})

    def calls(self) -> list[dict[str, Any]]:
        return _calls(self.pool)

    def actions(self) -> list[str]:
        return [r["action"] for r in self.pool.rows]


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _expected(
    path: Scenario,
    *,
    outcome: str,
    engine: str = "local",
    models: dict[str, str] | None = None,
    upto: int | None = None,
) -> list[dict[str, Any]]:
    models = models or LOCAL_MODELS
    rows = [
        {"job": job, "engine": engine if role == "extraction" else "local", "model": models[role],
         "outcome": outcome, "via": path.via}
        for job, role in path.jobs
    ]  # fmt: skip
    return rows if upto is None else rows[:upto]


# --- item 2: one record per call, naming who, which case, which engine and model ------------------


@pytest.mark.parametrize("name", list(PATHS))
def test_each_path_records_every_call_it_makes(name: str) -> None:
    run = Run(PATHS[name])
    answer = run.post()
    assert answer.status_code == 200, answer.text
    assert run.calls() == _expected(PATHS[name], outcome="answered")
    # The access row the route already wrote is still written, and the calls come first.
    assert run.actions()[-1] == PATHS[name].via
    assert _leaks(run.pool) == []


def test_a_hosted_engine_is_named_as_the_routing_chose_it() -> None:
    """The engine and model are the registry's record of the target: the deployment's default for
    the role, a hosted engine, with its model as the gateway names it."""
    run = Run(PATHS["run_extraction"], hosted=True)
    assert run.post().status_code == 200
    assert run.calls() == [
        {
            "job": "extract",
            "engine": "gemini",
            "model": "gemini/flash",
            "outcome": "answered",
            "via": "run_extraction",
        }  # fmt: skip
    ]


def test_an_engine_the_request_named_and_the_routing_replaced_is_recorded_as_the_one_used() -> None:
    """Gemini is named; nothing is sendable on this deployment, so it runs locally. The row says
    local, never gemini (the brief's item 2; `model_routing.py` decision 2)."""
    run = Run(PATHS["ask"])
    assert run.post(engine="gemini").status_code == 200
    assert run.calls() == _expected(PATHS["ask"], outcome="answered")
    assert [c["engine"] for c in run.calls()] == ["local"]


@pytest.mark.parametrize("name", ["ask", "pattern_ask"])
def test_a_refusal_before_any_engine_was_chosen_names_none(name: str) -> None:
    run = Run(PATHS[name])
    answer = run.post(engine="not-an-engine")
    assert answer.status_code != 200
    assert run.inner.calls == 0
    assert run.calls() == [
        {
            "job": PATHS[name].jobs[0][0],
            "engine": None,
            "model": None,
            "outcome": "refused",
            "via": PATHS[name].via,
        }  # fmt: skip
    ]
    assert PATHS[name].via not in run.actions()  # no answer, so no access row, as before


# --- item 4, before any engine is chosen: the egress refusal, an error and a cancel ---------------


@pytest.mark.parametrize("egress", ["none", "contracted"])
@pytest.mark.parametrize("name", list(PATHS))
def test_a_data_egress_refusal_is_recorded_as_refused_and_its_words_stay_out(
    name: str, egress: str
) -> None:
    """The deployment's default for the role is a hosted engine, it has no local model for it, and
    the case's dataset may not go there (`model_routing.choose` raises `ModelEgressRefused`). No
    engine was chosen, so the row names none; the words of the refusal, which name the dataset, are
    said to the person and are in no column of any row. `contracted` is refused because this
    stand-in hosted engine's contract is not the one the dataset's rule asks for (ADR-136)."""
    from services.api.model_routing import Engine

    run = Run(PATHS[name], hosted=True, egress=egress, no_local=True)
    if egress == "contracted":
        gemini = run.routed.routes.engines["gemini"]
        run.routed.set_routes(
            ModelRoutes(
                locals=run.routed.routes.locals,
                engines={"gemini": Engine(gemini.name, gemini.label, gemini.models, True)},
                defaults=run.routed.routes.defaults,
                sendable=run.routed.routes.sendable,
            )
        )
    answer = run.post()
    assert answer.status_code != 200, answer.text
    if name in ("run_extraction", "ask"):  # the paths whose words name the dataset
        assert DATASET in answer.text, "the person is still told which dataset"
    # A document's vision or speech call has no hosted engine on this deployment, so it runs
    # locally and is answered; the extraction after it is the one refused.
    before = len(PATHS[name].jobs) - 1
    assert run.inner.calls == before
    assert run.calls() == [
        *_expected(PATHS[name], outcome="answered", upto=before),
        {
            "job": PATHS[name].jobs[-1][0],
            "engine": None,
            "model": None,
            "outcome": "refused",
            "via": PATHS[name].via,
        },
    ]
    assert _leaks(run.pool) == []
    assert PATHS[name].via not in run.actions()


async def _ask_through_the_routing(reader: Any, pool: _Pool) -> None:
    """A call whose datasets' egress is read from `reader`, made inside an attributed block through
    `RoutedModel` as the routes make it."""
    from services.api import model_calls

    routed = RoutedModel(
        _Inner({}),  # type: ignore[arg-type]
        routes=_routes(hosted_default=True),
        egress=reader,
    )
    async with model_calls.attributed(
        AuditWriter(pool),  # type: ignore[arg-type]
        ACTING,
        CASE,
        job="ask",
        via="ask_question",  # type: ignore[arg-type]
    ):
        await routed.extract(
            ExtractionRequest(
                document_id="d", text=PROMPT, json_schema={}, model="x", handling=HANDLING,
                datasets=["ds-1"],
            )
        )  # fmt: skip


class _EgressStore:
    """The store the datasets' egress is read from, failing or hanging as a real one does; its
    error carries an address and a key, as a transport's does."""

    def __init__(self, *, fail: bool = False, hang: bool = False) -> None:
        self.fail, self.hang = fail, hang
        self.asked = asyncio.Event()

    async def egress_of(self, ids: Any) -> dict[str, Any]:
        self.asked.set()
        if self.hang:
            await asyncio.Event().wait()
        raise OSError(f"{ADDRESS} refused (key {KEY}) for {PROMPT}")


async def test_a_failure_reading_the_datasets_before_an_engine_is_chosen_is_errored() -> None:
    pool = _Pool()
    with pytest.raises(OSError):
        await _ask_through_the_routing(_EgressStore(fail=True), pool)
    assert _calls(pool) == [
        {"job": "ask", "engine": None, "model": None, "outcome": "errored", "via": "ask_question"}
    ]
    assert _leaks(pool) == []


async def test_a_call_cancelled_before_an_engine_is_chosen_is_recorded_as_interrupted() -> None:
    """The person closes the page while the routing is still reading the datasets' egress: no
    engine had been chosen, so the row says none (`_decided`'s cancel branch)."""
    pool = _Pool()
    reader = _EgressStore(hang=True)
    task = asyncio.create_task(_ask_through_the_routing(reader, pool))
    await reader.asked.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _calls(pool) == [
        {
            "job": "ask",
            "engine": None,
            "model": None,
            "outcome": "interrupted",
            "via": "ask_question",
        }  # fmt: skip
    ]
    assert _leaks(pool) == []


# --- item 4: a refused or failed call is recorded too --------------------------------------------


@pytest.mark.parametrize("name", list(PATHS))
@pytest.mark.parametrize("failure", list(FAILURES))
def test_a_refused_or_failed_call_is_recorded_with_its_engine_and_never_its_words(
    name: str, failure: str
) -> None:
    outcome, make = FAILURES[failure]
    run = Run(PATHS[name])
    run.inner.failure = make()
    answer = run.post()
    assert answer.status_code != 200
    # The first call fails, so nothing after it is made.
    assert run.calls() == _expected(PATHS[name], outcome=outcome, upto=1)
    assert _leaks(run.pool) == []
    assert PATHS[name].via not in run.actions()


def test_the_words_a_person_is_told_are_unchanged() -> None:
    """The refusals' status and words, measured on main before this slice, pinned (item 4)."""
    run = Run(PATHS["ask"])
    run.inner.failure = ModelLimitReached("requests")
    limit = run.post()
    run = Run(PATHS["ask"])
    refused = run.post(engine="not-an-engine")
    run = Run(PATHS["email"])
    run.inner.failure = _leaky(ModelUnavailableError)
    unavailable = run.post()
    assert (limit.status_code, limit.json()["error"]) == (429, "model_limit_reached")
    assert "has reached its limit of requests a minute" in limit.json()["detail"]
    assert (refused.status_code, refused.json()["error"]) == (422, "engine_refused")
    assert "not-an-engine is not an engine this deployment enabled" in refused.json()["detail"]
    assert (unavailable.status_code, unavailable.json()["error"]) == (503, "model_unavailable")


@pytest.mark.parametrize("name", list(PATHS))
def test_a_person_with_no_right_to_the_case_records_nothing_and_learns_nothing(name: str) -> None:
    """Rule 4: the stranger is told what a case that does not exist is told (same status, same
    words), no model is called and no `model_call` row, or any row, is written."""
    path = PATHS[name]
    run = Run(path, principal=STRANGER)
    refused = run.post()
    run.pool.rows.clear()
    missing = run.client.post(path.url.replace(CASE, "inv-9"), json=path.body())
    assert refused.status_code == missing.status_code == 404
    assert refused.json() == missing.json()
    assert run.inner.calls == 0
    # What the refusal already wrote (`access_denied`, which names no model) and nothing of a call.
    assert {r["action"] for r in run.pool.rows} <= {"access_denied"}
    assert run.calls() == [] and _leaks(run.pool) == []


@pytest.mark.parametrize("name", ["ask", "run_extraction"])
def test_a_failed_audit_write_fails_closed_and_no_answer_is_returned(name: str) -> None:
    run = Run(PATHS[name])
    run.pool.down_for = {"model_call"}
    answer = run.post()
    assert answer.status_code == 503, answer.text
    assert PATHS[name].via not in run.actions()


# --- the embed job: no route embeds today; the routing's own record of it is tested here ---------


class _EmbedClient:
    """The gateway client as the adapter calls it for an embedding: it keeps the model it was asked
    for (the one the adapter was built with), and it fails as asked."""

    def __init__(self) -> None:
        self.asked_for: list[str] = []
        self.failure: Exception | None = None
        self.api_key = KEY
        self.base_url = ADDRESS

    async def embed(self, model: str, texts: Any) -> list[list[float]]:
        self.asked_for.append(model)
        if self.failure is not None:
            raise self.failure
        return [[0.0] for _ in texts]


def _embedding_through_the_routing(embedding: str, *, hosted: bool = False) -> tuple[Any, Any]:
    """`RoutedModel` over the real `ModelLiteLLMAdapter`, both built from one `DeploymentModels` as
    `app.py` builds them (`embed_model=models.embedding`, `routes_from_env(models, …)`)."""
    from services.api.config import DeploymentModels
    from services.api.model_routing import routes_from_env

    from adapters.model_litellm.adapter import ModelLiteLLMAdapter

    models = DeploymentModels(
        extraction="qwen-local", vision="vision-local", transcription="speech-local",
        embedding=embedding,
    )  # fmt: skip
    client = _EmbedClient()
    environ = {
        "OSPREY_MODEL_ENGINES": '[{"name": "gemini", "label": "Gemini", "roles": '
        '{"embedding": "gemini/embed"}, "privacy_contract": true}]',
        "OSPREY_MODEL_DEFAULTS": '{"embedding": "gemini"}' if hosted else "{}",
        "OSPREY_MODEL_KEY_PRESENT_GEMINI": "yes",
    }
    routed = RoutedModel(
        ModelLiteLLMAdapter(client, embed_model=models.embedding),  # type: ignore[arg-type]
        routes=routes_from_env(models, environ),
    )
    return routed, client


async def _embed(routed: Any, pool: _Pool) -> list[list[float]]:
    from services.api import model_calls

    async with model_calls.attributed(
        AuditWriter(pool),  # type: ignore[arg-type]
        ACTING,
        CASE,
        job="ask",
        via="ask_question",  # type: ignore[arg-type]
    ):
        return await routed.embed([f"text {PROMPT}"])


def _embed_row(model: str, outcome: str) -> dict[str, Any]:
    return {
        "job": "embed", "engine": "local", "model": model, "outcome": outcome,
        "via": "ask_question",
    }  # fmt: skip


@pytest.mark.parametrize("hosted", [False, True])
async def test_an_embed_call_is_recorded_as_the_local_model_the_adapter_sent(hosted: bool) -> None:
    """The embedding never leaves (`RoutedModel.embed`): even where the deployment's default for the
    role names a hosted engine, the row names `local` and the model the adapter really sent, which
    the client was asked for, not a name made up beside it."""
    embedding = "embed-" + secrets.token_hex(4)
    routed, client = _embedding_through_the_routing(embedding, hosted=hosted)
    pool = _Pool()
    assert await _embed(routed, pool) == [[0.0]]
    assert client.asked_for == [embedding]
    assert _calls(pool) == [_embed_row(embedding, "answered")]
    assert _leaks(pool) == []


@pytest.mark.parametrize(
    ("failure", "outcome"),
    [(_leaky(), "errored"), (ModelLimitReached("requests"), "refused"), (None, "interrupted")],
)
async def test_a_failed_refused_or_cancelled_embed_is_recorded_without_its_words(
    failure: Exception | None, outcome: str
) -> None:
    routed, client = _embedding_through_the_routing("embed-local")
    pool = _Pool()
    if failure is None:  # the call is cancelled while it waits
        started = asyncio.Event()

        async def hang(model: str, texts: Any) -> list[list[float]]:
            started.set()
            await asyncio.Event().wait()
            return []

        client.embed = hang  # type: ignore[method-assign]
        task = asyncio.create_task(_embed(routed, pool))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        client.failure = failure
        with pytest.raises(type(failure)):
            await _embed(routed, pool)
    assert _calls(pool) == [_embed_row("embed-local", outcome)]
    assert _leaks(pool) == []


def test_an_embed_that_is_not_noted_is_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """The routing's wrapper at `embed` removed (the planted fault of the finding): the block
    records nothing, so the check that the row is there fails."""

    @contextmanager
    def nothing(self: Any, *args: Any, **kwargs: Any) -> Any:
        yield

    monkeypatch.setattr(RoutedModel, "_noted", nothing)
    routed, _ = _embedding_through_the_routing("embed-local")
    pool = _Pool()
    asyncio.run(_embed(routed, pool))
    with pytest.raises(AssertionError):
        assert _calls(pool) == [_embed_row("embed-local", "answered")]


def test_an_embed_recorded_under_another_model_name_is_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """The row's model taken from somewhere other than the model the adapter sent (here the
    extraction model, a plausible slip in `routes.locals[…]`): the comparison with what the client
    was asked for fails."""
    real = RoutedModel._noted

    def wrong(self: Any, job: str, engine: str, model: str | None) -> Any:
        return real(self, job, engine, self.routes.locals.get("extraction"))

    monkeypatch.setattr(RoutedModel, "_noted", wrong)
    routed, client = _embedding_through_the_routing("embed-local")
    pool = _Pool()
    asyncio.run(_embed(routed, pool))
    assert client.asked_for == ["embed-local"]
    with pytest.raises(AssertionError):
        assert _calls(pool) == [_embed_row(client.asked_for[0], "answered")]


# --- the call that is cancelled ------------------------------------------------------------------


async def test_a_cancelled_call_is_recorded_as_interrupted() -> None:
    """The person closes the page while the model is working: the row is still written, with
    the engine and model the routing had chosen (the write is shielded from the cancel)."""
    from services.api import model_calls

    pool = _Pool()
    inner = _Inner({})
    inner.hang = True
    routed = RoutedModel(inner, routes=_routes())  # type: ignore[arg-type]

    async def asking() -> None:
        async with model_calls.attributed(
            AuditWriter(pool),
            ACTING,
            CASE,
            job="ask",
            via="ask_question",  # type: ignore[arg-type]
        ):
            await routed.extract(
                ExtractionRequest(
                    document_id="d", text=PROMPT, json_schema={}, model="x", handling=None
                )
            )

    task = asyncio.create_task(asking())
    await inner.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _calls(pool) == [
        {
            "job": "ask",
            "engine": "local",
            "model": "qwen-local",
            "outcome": "interrupted",
            "via": "ask_question",
        }  # fmt: skip
    ]
    assert _leaks(pool) == []


async def test_a_call_made_outside_any_attribution_still_runs_and_records_nothing() -> None:
    """A caller with no person or case has no row to write; the scan below is what makes sure
    no route is such a caller by omission."""
    routed = RoutedModel(_Inner({"x": 1}), routes=_routes())  # type: ignore[arg-type]
    result = await routed.extract(
        ExtractionRequest(document_id="d", text="t", json_schema={}, model="x", handling=None)
    )
    assert result.data == {"x": 1}


# --- item 3: nothing but names, and the fault that would write more is red ------------------------


def _plant(monkeypatch: pytest.MonkeyPatch, add: str) -> None:
    """The recording code made to write `add` into the call's engine, as a careless change to
    the code that builds the record would: through the real `note`, at the call site the routing
    uses."""
    import dataclasses

    from services.api import model_calls

    real = model_calls.note

    def careless(call: Any) -> None:
        real(dataclasses.replace(call, model=f"{call.model} {add}"))

    monkeypatch.setattr(model_calls, "note", careless)


@pytest.mark.parametrize("kind", list(SECRETS))
@pytest.mark.parametrize("name", list(PATHS))
def test_the_leak_check_is_red_when_the_record_carries_a_prompt_an_address_or_a_key(
    name: str, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Run(PATHS[name])
    _plant(monkeypatch, SECRETS[kind])
    assert run.post().status_code == 200
    assert _leaks(run.pool) != []
    with pytest.raises(AssertionError):
        assert run.calls() == _expected(PATHS[name], outcome="answered")


def test_the_record_is_red_when_an_errors_own_text_is_written_as_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shape an error handler would take: `str(exc)` carried into the row. The stand-in's
    errors hold the address and the key, as a transport's do."""
    import dataclasses

    from services.api import model_calls

    real = model_calls.note
    fields = {f.name for f in dataclasses.fields(model_calls.ModelCall)}
    assert fields == {"job", "engine", "model", "outcome"}  # nothing free-text to carry words in

    def careless(call: Any) -> None:
        real(dataclasses.replace(call, model=f"{call.model} {run.inner.failure}"))

    run = Run(PATHS["ask"])
    run.inner.failure = _leaky()
    monkeypatch.setattr(model_calls, "note", careless)
    run.post()
    assert {"key in model_call", "address in model_call"} <= set(_leaks(run.pool))


# --- item 5: the path that stops writing its record is red ---------------------------------------


@pytest.mark.parametrize("name", list(PATHS))
def test_a_path_that_stops_recording_is_red(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The attribution removed at the route's own site (the route asks `model_calls.attributed`
    each time, so replacing it with a block that records nothing is that deletion)."""
    from services.api import model_calls

    @asynccontextmanager
    async def nothing(*args: Any, **kwargs: Any) -> Any:
        yield

    monkeypatch.setattr(model_calls, "attributed", nothing)
    run = Run(PATHS[name])
    assert run.post().status_code == 200
    with pytest.raises(AssertionError):
        assert run.calls() == _expected(PATHS[name], outcome="answered")


def test_an_engine_taken_from_the_request_body_is_red(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    from services.api import model_calls

    real = model_calls.note

    def from_the_request(call: Any) -> None:
        real(dataclasses.replace(call, engine="gemini"))

    monkeypatch.setattr(model_calls, "note", from_the_request)
    run = Run(PATHS["ask"])
    run.post(engine="gemini")
    with pytest.raises(AssertionError):
        assert run.calls() == _expected(PATHS["ask"], outcome="answered")


# --- the scans -----------------------------------------------------------------------------------

#: The port's methods. A call is found by the method alone, **whatever the object is called**
#: (`routed.extract`, `held.embed`, `self._brain.transcribe`): the routing wrapper is held under
#: many names, and a name list would let the next one through. What the scan finds that is not the
#: port (a zip archive's `extract`, a service's own `extract`) is named in `REVIEWED_CALLERS`, with
#: the reason. A method taken without being called (`fn = routed.embed`) is found as well.
_METHODS = {"extract", "transcribe", "describe_image", "embed"}
#: What a file imports to hold the port: the port, its gateway adapter, Laurium's, or the routing
#: wrapper (`from .model_routing import …`, `from services.api import model_routing`).
_PORT_IMPORTS = ("ports.model", "adapters.model_litellm", "adapters.extract_laurium")
_ROUTING = "model_routing"
_CALL_FOLDERS = ("services", "scripts", "harness", "cli", "connectors")
_FILE_FOLDERS = (*_CALL_FOLDERS, "packages")
#: The adapters that implement the port and the folders that declare it are the port, not callers.
_PORT_ITSELF = ("packages/adapters/model_litellm", "packages/adapters/extract_laurium",
                "packages/ports", "packages/schemas")  # fmt: skip

#: Every function that calls the model port (path, qualified function, receiver.method), with who
#: asked, which case, and whether the call is recorded. A new one fails the scan until it is here.
REVIEWED_CALLERS: dict[tuple[str, str, str], str] = {
    ("services/api/questions.py", "QuestionsService.ask", "self._model.extract"):
        "ask the case: the asker, the case; recorded by ask_question_route (job ask)",
    ("services/api/review.py", "run_extraction", "model.extract"):
        "extraction; the asker, the case; recorded by the run_extraction, extract_email and "
        "extract_document routes, one row per window (jobs extract, email)",
    ("services/api/pattern_ask.py", "PatternProposer.propose", "self._model.extract"):
        "ask to search: the asker, the case; recorded by ask_to_search_route (job pattern_ask)",
    ("services/api/document_content.py", "DocumentContentService._text_of",
     "self._model.describe_image"):
        "a held image: the extractor, the case; recorded by extract_document_route (job describe)",
    ("services/api/document_content.py", "DocumentContentService._text_of",
     "self._model.transcribe"):
        "a held video: the extractor, the case; recorded by extract_document_route "
        "(job transcribe)",
    ("services/api/model_routing.py", "RoutedModel.extract", "self._inner.extract"):
        "the routing itself: where each call is noted with the engine and model it chose",
    ("services/api/model_routing.py", "RoutedModel.transcribe", "self._inner.transcribe"):
        "the routing itself (as above)",
    ("services/api/model_routing.py", "RoutedModel.describe_image", "self._inner.describe_image"):
        "the routing itself (as above)",
    ("services/api/model_routing.py", "RoutedModel.embed", "self._inner.embed"):
        "the routing itself; no caller embeds today. A call made outside an attributed block is "
        "noted nowhere (`model_calls.note`), so a new caller is recorded only once its route "
        "attributes it: this list is where that is reviewed",
    ("services/api/app.py", "extract_email_route", "email_extraction.extract"):
        "a route asking the email service, which runs `review.run_extraction`; inside the "
        "route's attributed block (the route scan)",
    ("services/api/app.py", "extract_document_route", "document_content.extract"):
        "a route asking the document service, which makes the describe, transcribe and extract "
        "calls; inside the route's attributed block (the route scan)",
    ("scripts/pages_image_react_scan.py", "extract_app", "archive.extract"):
        "not a model: a zip archive's `extract`",
    ("scripts/build_local_basemap.py", "_run", "args.extract"):
        "not a model: a command-line flag (`--extract`) of the basemap build",
}  # fmt: skip

#: Every file that imports the port, the gateway adapter or Laurium's, with why it is not a caller
#: above (or which it is).
REVIEWED_FILES: dict[str, str] = {
    "services/api/app.py": "builds the model and passes it to the services; its routes are the "
    "second scan's",
    "services/api/questions.py": "caller, listed",
    "services/api/review.py": "caller, listed",
    "services/api/pattern_ask.py": "caller, listed",
    "services/api/document_content.py": "caller, listed",
    "services/api/email_extraction.py": "holds the port and calls run_extraction (listed)",
    "services/api/model_routing.py": "the routing, listed",
    "services/api/laurium_start.py": "composes Laurium inside the routing at start-up; makes no "
    "model call of its own (it holds the key at the gateway)",
    "services/api/model_keys.py": "reads the gateway's configuration for key storage; sends no "
    "prompt",
    "services/api/model_usage.py": "reads the gateway's usage counts; no call to a model",
    "services/api/model_admin.py": "Admin › Models: the connection test records its engine itself "
    "(AD1a's file, not edited here; SE-AD1b owns its audit)",
}


def _routing(name: str) -> bool:
    return name == _ROUTING or name.endswith(f".{_ROUTING}")


def _imports_port(tree: ast.Module) -> bool:
    """The file imports the port, an adapter that implements it, or the routing wrapper (by module,
    absolute or relative, or as a name taken from its package)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module.startswith(_PORT_IMPORTS) or _routing(node.module)):
                return True
            if any(a.name == _ROUTING for a in node.names):
                return True
        if isinstance(node, ast.Import):
            if any(a.name.startswith(_PORT_IMPORTS) or _routing(a.name) for a in node.names):
                return True
    return False


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return node.id if isinstance(node, ast.Name) else "?"


def model_port_callers(core: pathlib.Path = CORE) -> tuple[set[tuple[str, str, str]], set[str]]:
    """(calls, files) found under `core`: every `<anything>.extract|transcribe|describe_image|embed`
    in the call folders, with its enclosing function; every file importing the port or the
    routing."""
    calls: set[tuple[str, str, str]] = set()
    files: set[str] = set()
    for folder in _FILE_FOLDERS:
        for path in sorted((core / folder).rglob("*.py")):
            rel = path.relative_to(core).as_posix()
            if rel.startswith(_PORT_ITSELF):
                continue
            tree = ast.parse(path.read_text())
            if _imports_port(tree):
                files.add(rel)
            if folder not in _CALL_FOLDERS:
                continue

            class Visit(ast.NodeVisitor):
                def __init__(self) -> None:
                    self.stack: list[str] = []

                def _scope(self, node: Any) -> None:
                    self.stack.append(node.name)
                    self.generic_visit(node)
                    self.stack.pop()

                visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope

                def visit_Attribute(self, node: ast.Attribute) -> None:
                    if node.attr in _METHODS:
                        calls.add((rel, ".".join(self.stack), f"{_dotted(node.value)}.{node.attr}"))
                    self.generic_visit(node)

            Visit().visit(tree)
    return calls, files


def test_every_model_port_caller_is_one_the_list_names() -> None:
    calls, files = model_port_callers()
    assert sorted(calls - set(REVIEWED_CALLERS)) == []
    assert sorted(set(REVIEWED_CALLERS) - calls) == [], "a listed caller has gone: update the list"
    assert sorted(files - set(REVIEWED_FILES)) == []
    assert sorted(set(REVIEWED_FILES) - files) == [], "a listed file no longer imports the port"


def test_the_scan_finds_the_callers_it_claims_to() -> None:
    """A scan that found nothing would pass the test above."""
    calls, files = model_port_callers()
    assert len(calls) >= 12 and len(files) >= 10
    assert {c[2] for c in calls} >= {"self._model.extract", "model.extract", "self._inner.embed"}
    # Whatever the object is called: a zip archive's `extract` and the routes' services are found.
    assert {c[2] for c in calls} >= {"archive.extract", "document_content.extract"}


def _copy_services(tmp_path: pathlib.Path) -> pathlib.Path:
    core = tmp_path / "OspreyFlow_Core"
    for folder in (*_FILE_FOLDERS, "packages"):
        if (CORE / folder).exists() and not (core / folder).exists():
            shutil.copytree(CORE / folder, core / folder, ignore=shutil.ignore_patterns(
                "__pycache__", "node_modules"))  # fmt: skip
    return core


def test_a_new_caller_of_the_model_port_is_found(tmp_path: pathlib.Path) -> None:
    """Planted at the shape the services use: a function of a new service calling
    `self._model.extract`, a worker holding the gateway adapter, and a file importing the port
    that calls it under a name of its own."""
    core = _copy_services(tmp_path)
    (core / "services" / "ingest" / "planted_summary.py").write_text(
        "class Summary:\n"
        "    async def summarise(self, req):\n"
        "        return await self._model.extract(req)\n"
    )
    (core / "services" / "worker_planted.py").write_text(
        "from ports.model import ModelPort\n\n"
        "async def nightly(engine: ModelPort, req):\n"
        "    return await engine.embed(req)\n"
    )
    calls, files = model_port_callers(core)
    assert calls - set(REVIEWED_CALLERS) == {
        ("services/ingest/planted_summary.py", "Summary.summarise", "self._model.extract"),
        ("services/worker_planted.py", "nightly", "engine.embed"),
    }
    assert files - set(REVIEWED_FILES) == {"services/worker_planted.py"}


def test_a_caller_holding_the_routing_under_another_name_is_found(tmp_path: pathlib.Path) -> None:
    """The shape a real change takes (rule 15), at the real sites: `await routed.extract(…)` added
    in `QuestionsService.will_read`, which already binds `routed` and is reached from a route with
    no attributed block; a new service that imports the routing relatively and holds it as `held`;
    and a method taken without being called. None has a receiver the old name list knew."""
    core = _copy_services(tmp_path)
    questions = core / "services" / "api" / "questions.py"
    source = questions.read_text()
    line = "        routed = self._model if isinstance(self._model, RoutedModel) else None\n"
    assert source.count(line) == 1
    questions.write_text(source.replace(line, line + "        await routed.extract(None)\n"))
    (core / "services" / "api" / "planted_digest.py").write_text(
        "from .model_routing import RoutedModel\n\n"
        "class Digest:\n"
        "    def __init__(self, held: RoutedModel) -> None:\n"
        "        self.held = held\n\n"
        "    async def nightly(self, req):\n"
        "        send = self.held.describe_image\n"
        "        return await send(req)\n"
    )
    calls, files = model_port_callers(core)
    assert calls - set(REVIEWED_CALLERS) == {
        ("services/api/questions.py", "QuestionsService.will_read", "routed.extract"),
        ("services/api/planted_digest.py", "Digest.nightly", "self.held.describe_image"),
    }
    assert files - set(REVIEWED_FILES) == {"services/api/planted_digest.py"}


def test_every_way_a_file_can_import_the_routing_is_seen() -> None:
    for source in (
        "from .model_routing import RoutedModel",
        "from services.api.model_routing import RoutedModel",
        "from services.api import model_routing",
        "from . import model_routing",
        "import services.api.model_routing",
        "from ports.model import ModelPort",
        "from adapters.model_litellm.client import LiteLLMModel",
    ):
        assert _imports_port(ast.parse(source)), source
    for source in ("from .model_calls import attributed", "import json", "from . import audit"):
        assert not _imports_port(ast.parse(source)), source


def test_a_listed_caller_that_has_gone_is_found(tmp_path: pathlib.Path) -> None:
    core = _copy_services(tmp_path)
    path = core / "services" / "api" / "pattern_ask.py"
    path.write_text(path.read_text().replace("self._model.extract(", "self._model.guess("))
    calls, _ = model_port_callers(core)
    assert ("services/api/pattern_ask.py", "PatternProposer.propose",
            "self._model.extract") not in calls  # fmt: skip


# --- the third scan: whatever reaches the model, by whatever name, is asked in an attribution ---

#: What the third scan reads: the folders the port's callers are searched in.
_REACH_FOLDERS = _CALL_FOLDERS
#: The block that attributes a call: `async with model_calls.attributed(…)`.
_ATTRIBUTING = "model_calls.attributed"
#: Not a model, though its method is called `extract`: from the first scan's own list.
_NOT_A_MODEL = {key for key, why in REVIEWED_CALLERS.items() if why.startswith("not a model")}


@dataclass
class _Ref:
    name: str
    #: Inside an attributing block of the function that holds it.
    guarded: bool
    #: In the signature (decorators, parameters, annotations, defaults), not the body.
    signature: bool
    line: int
    #: The dotted text if the reference is an attribute (`self._model.extract`), else "".
    full: str


@dataclass
class _Fn:
    """One function (or the module's own top level), the class that holds it, every name it refers
    to, and what its parameters and local names are declared or assigned to be."""

    path: str
    qualname: str
    name: str
    cls: str | None
    refs: list[_Ref]
    #: local name -> the type names it was annotated with, or copied or constructed from
    types: dict[str, list[str]]
    #: The file: `objs` local name -> (module, name) for `from m import name as local`; `mods`
    #: local name -> module for `import a.m as local` and `from a import m as local`; `attrs`
    #: class -> attribute -> type names, from `self.x = param` with an annotated `param`.
    objs: dict[str, tuple[str, str]]
    mods: dict[str, str]
    attrs: dict[str, dict[str, list[str]]]

    @property
    def stem(self) -> str:
        return pathlib.PurePosixPath(self.path).stem


@dataclass
class _Alias:
    """A module-level name made of others (`QuestionsDep = Annotated[QuestionsService, …]`): what
    the routes' signatures name instead of the class."""

    stem: str
    name: str
    of: list[str]
    objs: dict[str, tuple[str, str]]


def _names_in(node: ast.AST | None) -> list[str]:
    return [] if node is None else [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]


def _functions_of(rel: str, tree: ast.Module) -> tuple[list[_Fn], list[_Alias]]:
    """Every function of a file, a nested one apart from the one that holds it. A name is a
    reference whether it is called or only taken (`add_task(digest, …)`, `send = held.embed`, a
    parameter's annotation `svc: QuestionsService`): each `ast.Name` (by id) and `ast.Attribute`
    (by attribute)."""
    out: list[_Fn] = []
    objs: dict[str, tuple[str, str]] = {}
    mods: dict[str, str] = {}
    attrs: dict[str, dict[str, list[str]]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module.split(".")[-1] if node.module else ""
            for a in node.names:
                objs[a.asname or a.name] = (module, a.name)
                mods[a.asname or a.name] = a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                mods[a.asname or a.name.split(".")[0]] = a.name.split(".")[-1]

    def declare(fn: _Fn, node: ast.AST, cls: str | None) -> None:
        """What a name is: a parameter's annotation, `x: T = …`, `x = y` (y's), `x = T(…)`, and
        `self.x = param` for the class's other methods."""
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            args = node.args
            for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                fn.types[a.arg] = _names_in(a.annotation) if a.annotation else []
        for n in ast.walk(node):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(n, ast.Assign):
                targets, value = n.targets, n.value
            elif isinstance(n, ast.AnnAssign):
                targets, value = [n.target], n.value
                if isinstance(n.target, ast.Name):
                    fn.types.setdefault(n.target.id, []).extend(_names_in(n.annotation))
            for t in targets:
                held: list[str] = []
                if isinstance(value, ast.Name):
                    held = fn.types.get(value.id, [])
                elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                    held = [value.func.id]
                elif isinstance(value, ast.Attribute) and ".state." in f".{_dotted(value)}":
                    held = [f"state:{value.attr}"]  # `request.app.state.questions`
                if isinstance(t, ast.Attribute) and ".state." in f".{_dotted(t)}":
                    attrs.setdefault("state", {}).setdefault(t.attr, []).extend(held)
                    continue
                if isinstance(t, ast.Name):
                    fn.types.setdefault(t.id, []).extend(held)
                elif (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                      and t.value.id == "self" and cls):  # fmt: skip
                    attrs.setdefault(cls, {}).setdefault(t.attr, []).extend(held)

    def walk(
        node: ast.AST, fn: _Fn, guarded: bool, signature: bool, stack: list[str], cls: str | None
    ) -> None:
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            inner = _Fn(
                rel, ".".join([*stack, node.name]), node.name, cls, [], {}, objs, mods, attrs
            )
            out.append(inner)
            declare(inner, node, cls)
            for child in (
                *node.decorator_list,
                node.args,
                *([node.returns] if node.returns else []),
            ):
                walk(child, inner, False, True, [*stack, node.name], cls)
            for child in node.body:
                walk(child, inner, False, False, [*stack, node.name], cls)
            return
        if isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                walk(child, fn, guarded, signature, [*stack, node.name], cls or node.name)
            return
        if isinstance(node, ast.Name):
            fn.refs.append(_Ref(node.id, guarded, signature, node.lineno, ""))
        elif isinstance(node, ast.Attribute):
            fn.refs.append(_Ref(node.attr, guarded, signature, node.lineno, _dotted(node)))
        if isinstance(node, ast.AsyncWith | ast.With):
            attributing = any(
                isinstance(i.context_expr, ast.Call)
                and _dotted(i.context_expr.func) == _ATTRIBUTING
                for i in node.items
            )
            for item in node.items:
                walk(item, fn, guarded, signature, stack, cls)
            for child in node.body:
                walk(child, fn, guarded or attributing, signature, stack, cls)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, fn, guarded, signature, stack, cls)

    top = _Fn(rel, "<module>", "<module>", None, [], {}, objs, mods, attrs)
    out.append(top)
    walk(tree, top, False, False, [], None)
    stem = pathlib.PurePosixPath(rel).stem
    aliases = []
    for node in tree.body:
        target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else (
            node.target if isinstance(node, ast.AnnAssign) else None
        )  # fmt: skip
        value = getattr(node, "value", None)
        if isinstance(target, ast.Name) and value is not None:
            aliases.append(_Alias(stem, target.id, _names_in(value), objs))
    return out, aliases


@functools.cache
def _parsed(rel: str, source: str) -> tuple[list[_Fn], list[_Alias]]:
    return _functions_of(rel, ast.parse(source))


def _files(core: pathlib.Path) -> tuple[list[_Fn], list[_Alias]]:
    fns: list[_Fn] = []
    aliases: list[_Alias] = []
    for folder in _REACH_FOLDERS:
        for path in sorted((core / folder).rglob("*.py")):
            f, a = _parsed(path.relative_to(core).as_posix(), path.read_text())
            fns.extend(f)
            aliases.extend(a)
    return fns, aliases


def _target(fn: _Fn, ref: _Ref) -> tuple[str, str] | None:
    """The (module, name) a reference points to, by what the file imports: a bare name is the one
    the file imported or defines; an attribute is a name taken from a module the file imported
    (`review_module.run_extraction`). A method (`svc.ask`) is resolved by what the receiver is
    declared to be, in `_reaching_ref`; a module's `digest` is not `hashlib`'s."""
    if not ref.full:
        return fn.objs.get(ref.name, (fn.stem, ref.name))
    owner, _, rest = ref.full.partition(".")
    if rest == ref.name and owner in fn.mods:
        return (fn.mods[owner], ref.name)
    return None


@dataclass
class _Reach:
    """What the fixed point has found so far."""

    #: (module, class) -> the names of its methods that reach a model
    holders: dict[tuple[str, str], set[str]]
    #: (module, name) of functions outside a class that reach a model
    functions: set[tuple[str, str]]
    #: (module, alias) -> the holder classes it stands for
    aliases: dict[tuple[str, str], set[tuple[str, str]]]
    #: method names that only reaching methods carry in the whole scanned tree
    unambiguous: set[str]


def _holders_of(fn: _Fn, receiver: str, reach: _Reach) -> set[tuple[str, str]]:
    """The holder classes `receiver` (`svc`, `self._proposer`) is declared to be."""
    if receiver.startswith("self.") and fn.cls and "." not in receiver[5:]:
        declared = fn.attrs.get(fn.cls, {}).get(receiver[5:], [])
    elif "." not in receiver:
        declared = fn.types.get(receiver, [])
    else:
        return set()
    found: set[tuple[str, str]] = set()
    for type_name in declared:
        if type_name.startswith("state:"):  # what the app built and put on its state
            for built in fn.attrs.get("state", {}).get(type_name[6:], []):
                key = fn.objs.get(built, (fn.stem, built))
                found |= {key} if key in reach.holders else set()
            continue
        key = fn.objs.get(type_name, (fn.stem, type_name))
        key = (fn.stem, type_name) if key not in reach.holders and key not in reach.aliases else key
        found |= reach.aliases.get(key, set()) | ({key} if key in reach.holders else set())
    return found


def _reaching_ref(fn: _Fn, r: _Ref, reach: _Reach) -> bool:
    """Whether the reference is to something that reaches a model."""
    if r.name in _METHODS:
        # A port method on any object, as the first scan reads one: not a variable of that name.
        return "." in r.full and (fn.path, fn.qualname, r.full) not in _NOT_A_MODEL
    if r.full:
        receiver = r.full.rpartition(".")[0]
        for key in _holders_of(fn, receiver, reach):
            if r.name in reach.holders[key]:
                return True
        if _target(fn, r) in reach.functions:
            return True
        # A receiver nothing declares: followed by the name alone where no other function has it.
        return (
            fn.path.startswith("services/")
            and not _holders_of(fn, receiver, reach)
            and r.name in reach.unambiguous
        )
    return _target(fn, r) in reach.functions


def reach_of(
    core: pathlib.Path = CORE,
) -> tuple[list[_Fn], list[_Fn], _Reach]:
    """(exposed, roots, reach) under `core`'s call folders.

    A function **reaches** the model when, outside an attributing block of its own, in its body,
    it refers to

    - a port method (`extract`, `transcribe`, `describe_image`, `embed`) as an attribute of any
      object, as the first scan reads one (a variable called `extract` is not one);
    - a reaching function outside a class (`run_extraction`, bare or as
      `review_module.run_extraction`, by the module it is imported from, whatever it is called
      locally); or
    - a method of a class that has one that reaches (a **holder**), on a receiver declared to be
      the holder: a parameter annotated with it or with an alias of it (`svc: QuestionsDep`), a
      name copied from or constructed as one (`svc = questions`, `svc = QuestionsService(…)`), or
      `self.x` assigned from such a parameter in the class, or a name taken off the app's state
      that the app built as one (`held = request.app.state.questions`); or such a method's name on
      a receiver nothing declares, if no other function in `services` has that name.

    That is a fixed point. A **root** is a function that reaches and that no other function refers
    to (a route, a worker, a new service nobody calls yet): the top of a chain with nothing
    attributing it. A route that asks inside `model_calls.attributed(…)` does not reach, so the
    chain ends there. Not followed: a receiver nothing declares whose method's name another
    function in `services` also has, and any receiver outside `services` (`getattr`, a service
    passed untyped through a helper): the first two scans are what find those."""
    fns, aliases = _files(core)
    defined: dict[str, int] = {}
    for f in fns:
        if f.path.startswith("services/"):
            defined[f.name] = defined.get(f.name, 0) + 1
    reach = _Reach({}, set(), {}, set())
    exposed: dict[int, _Fn] = {}
    changed = True
    while changed:
        changed = False
        for alias in aliases:
            made = {alias.objs.get(n, (alias.stem, n)) for n in alias.of} & set(reach.holders)
            if made and reach.aliases.get((alias.stem, alias.name)) != made:
                reach.aliases[(alias.stem, alias.name)] = made
                changed = True
        for fn in fns:
            if id(fn) in exposed or fn.name == "<module>":
                continue
            if any(
                not r.guarded and not r.signature and _reaching_ref(fn, r, reach) for r in fn.refs
            ):
                exposed[id(fn)] = fn
                if fn.cls:
                    reach.holders.setdefault((fn.stem, fn.cls), set()).add(fn.name)
                else:
                    reach.functions.add((fn.stem, fn.name))
                changed = True
        methods: dict[str, int] = {}
        for methods_of in reach.holders.values():
            for name in methods_of:
                methods[name] = methods.get(name, 0) + 1
        unambiguous = {n for n, c in methods.items() if defined.get(n, 0) == c}
        if unambiguous != reach.unambiguous:
            reach.unambiguous = unambiguous
            changed = True
    # What is referred to: a method by its attribute name (`svc.summarise`), any other function by
    # the module and name a reference resolves to (`hashlib`'s `.digest()` is not a `digest`).
    attributes = {r.name for fn in fns for r in fn.refs if r.full}
    targets = {_target(fn, r) for fn in fns for r in fn.refs}
    roots = [
        fn
        for fn in exposed.values()
        if not fn.name.startswith("__")
        and (fn.name not in attributes if fn.cls else (fn.stem, fn.name) not in targets)
    ]
    return list(exposed.values()), roots, reach


#: An exposed function nothing refers to, and why that is not an unattributed route to a model.
#: A scan hit is either a new caller to attribute (its route wraps the call in
#: `model_calls.attributed`) or, if it is not a model, a line here with the reason.
REVIEWED_ROOTS: dict[tuple[str, str], str] = {
    ("services/api/model_routing.py", "RoutedModel.embed"):
        "the routing's own `embed`: no caller embeds today. A new one is asked from a route inside "
        "`model_calls.attributed(…)`, or it appears here as an unreferred root of the scan",
}  # fmt: skip


def unattributed_roots(core: pathlib.Path = CORE) -> list[str]:
    _, roots, _ = reach_of(core)
    return sorted(
        f"{fn.path}:{fn.qualname}" for fn in roots if (fn.path, fn.qualname) not in REVIEWED_ROOTS
    )


def attributing_functions(core: pathlib.Path = CORE) -> set[str]:
    """The functions that ask something that reaches a model inside an attributing block."""
    fns, _ = _files(core)
    _, _, reach = reach_of(core)
    return {
        fn.name
        for fn in fns
        if any(r.guarded and not r.signature and _reaching_ref(fn, r, reach) for r in fn.refs)
    }


def test_every_chain_that_reaches_a_model_is_asked_inside_an_attribution() -> None:
    """Walks `OspreyFlow_Core/services` (every subfolder), `scripts`, `harness`, `cli` and
    `connectors`. No function that reaches a model is left unreferred to: each is called by another
    that attributes the call, however the route names the service."""
    assert unattributed_roots() == []


def test_the_reach_scan_finds_the_chains_it_claims_to() -> None:
    """A scan that found nothing would pass the test above: it sees the real chains, and the five
    routes as the places they are attributed."""
    exposed, _, reach = reach_of()
    assert {fn.qualname for fn in exposed} >= {
        "run_extraction",
        "QuestionsService.ask",
        "PatternProposer.propose",
        "PatternAskService.ask",
        "DocumentContentService._text_of",
        "RoutedModel.embed",
    }
    assert {c for _, c in reach.holders} >= {"QuestionsService", "PatternProposer", "RoutedModel",
                                             "DocumentContentService", "EmailExtractionService",
                                             "PatternAskService"}  # fmt: skip
    assert ("review", "run_extraction") in reach.functions
    assert {a for _, a in reach.aliases} >= {"QuestionsDep"}
    assert attributing_functions() >= {
        "ask_question_route",
        "ask_to_search_route",
        "extract_document_route",
        "extract_email_route",
        "run_extraction_route",
    }


def _copy_of_core(tmp_path: pathlib.Path) -> pathlib.Path:
    return _copy_services(tmp_path)


def _app_without(tmp_path: pathlib.Path, old: str, new: str) -> pathlib.Path:
    core = _copy_of_core(tmp_path)
    path = core / "services" / "api" / "app.py"
    source = path.read_text()
    assert old in source, old
    path.write_text(source.replace(old, new))
    return core


def test_a_new_service_reaching_the_model_through_run_extraction_is_found(
    tmp_path: pathlib.Path,
) -> None:
    """The finding's own shape: `services/api/case_digest.py` imports `run_extraction` from
    `.review` and calls it bare, the way `document_content.py` does. No port method, no listed
    entry point, no import of the port: nothing of the first two scans sees it."""
    core = _copy_of_core(tmp_path)
    (core / "services" / "api" / "case_digest.py").write_text(
        "from .review import run_extraction\n\n\n"
        "async def digest(model, req):\n"
        "    return await run_extraction(model, req)\n"
    )
    assert unattributed_roots(core) == ["services/api/case_digest.py:digest"]


def test_a_route_calling_a_service_under_another_name_is_found(tmp_path: pathlib.Path) -> None:
    """A new route in `app.py` that holds the questions service as `svc` and asks it with no
    attributing block: the route is the root, and the service's own `ask` is not."""
    core = _copy_of_core(tmp_path)
    path = core / "services" / "api" / "app.py"
    path.write_text(
        path.read_text() + "\n\nasync def digest_route(questions: QuestionsService, req):\n"
        "    svc = questions\n"
        "    return await svc.ask(req)\n"
    )
    assert unattributed_roots(core) == ["services/api/app.py:digest_route"]


def test_a_service_taken_off_the_app_state_is_found(
    tmp_path: pathlib.Path,
) -> None:
    """A route that takes the service off `request.app.state` and asks it, with no annotation:
    `app.state.questions` is built as the questions service, so `held` is one."""
    core = _copy_of_core(tmp_path)
    path = core / "services" / "api" / "app.py"
    path.write_text(
        path.read_text() + "\n\nasync def digest_route(request, req):\n"
        "    held = request.app.state.questions\n"
        "    return await held.ask(req)\n"
    )
    assert unattributed_roots(core) == ["services/api/app.py:digest_route"]


def test_a_chain_of_two_new_callers_is_found_at_its_top(tmp_path: pathlib.Path) -> None:
    """`nightly` calls `summarise` calls `run_extraction`, nothing attributing: the top of the
    chain is the one named, since `summarise` is called by it."""
    core = _copy_of_core(tmp_path)
    (core / "services" / "api" / "case_digest.py").write_text(
        "from .review import run_extraction\n\n\n"
        "async def summarise(model, req):\n"
        "    return await run_extraction(model, req)\n\n\n"
        "async def nightly(model, reqs):\n"
        "    return [await summarise(model, r) for r in reqs]\n"
    )
    assert unattributed_roots(core) == ["services/api/case_digest.py:nightly"]


def test_a_caller_handed_over_without_being_called_is_found(tmp_path: pathlib.Path) -> None:
    """`background.add_task(summarise, …)` takes the function, it does not call it: a reference
    outside an attribution is a call the scan has to see (here, `nightly` holds it)."""
    core = _copy_of_core(tmp_path)
    (core / "services" / "api" / "case_digest.py").write_text(
        "from .review import run_extraction\n\n\n"
        "async def summarise(model, req):\n"
        "    return await run_extraction(model, req)\n\n\n"
        "def nightly(background, req):\n"
        "    background.add_task(summarise, req)\n"
    )
    assert unattributed_roots(core) == ["services/api/case_digest.py:nightly"]


def test_a_new_route_that_attributes_its_call_is_not_found(tmp_path: pathlib.Path) -> None:
    """The same route, asked inside `model_calls.attributed(…)` at the shape `app.py` uses: clean.
    Without this the scan could be red for every new caller whatever it did."""
    core = _copy_of_core(tmp_path)
    (core / "services" / "api" / "case_digest.py").write_text(
        "from .review import run_extraction\n\n\n"
        "async def summarise(model, req):\n"
        "    return await run_extraction(model, req)\n"
    )
    path = core / "services" / "api" / "app.py"
    path.write_text(
        path.read_text() + "\n\nfrom .case_digest import summarise\n\n\n"
        "async def digest_route(audit, principal, model, req):\n"
        "    async with model_calls.attributed(audit, principal, 'inv-1', job='extract',\n"
        "                                      via='digest'):\n"
        "        return await summarise(model, req)\n"
    )
    assert unattributed_roots(core) == []


def test_every_attribution_removed_names_the_five_routes(tmp_path: pathlib.Path) -> None:
    """With every attribution made unrecognisable in a copy, the scan names the five routes and no
    other."""
    core = _app_without(tmp_path, "model_calls.attributed(", "unattributed(")
    named = sorted(f.split(":")[1] for f in unattributed_roots(core))
    assert named == ["ask_question_route", "ask_to_search_route", "extract_document_route",
                     "extract_email_route", "run_extraction_route"]  # fmt: skip


def test_a_route_that_stops_attributing_is_found(tmp_path: pathlib.Path) -> None:
    """Planted at the real site: `ask_question_route`'s own `async with` block, and nothing else,
    made into a plain call."""
    core = _copy_of_core(tmp_path)
    path = core / "services" / "api" / "app.py"
    source = path.read_text()
    head, _, rest = source.partition("async def ask_question_route(")
    body, sep, tail = rest.partition("\n\n\n@app.")
    assert "model_calls.attributed(" in body, "ask_question_route does not attribute"
    path.write_text(
        head
        + "async def ask_question_route("
        + body.replace("model_calls.attributed(", "unattributed(")
        + sep
        + tail
    )
    assert unattributed_roots(core) == ["services/api/app.py:ask_question_route"]
