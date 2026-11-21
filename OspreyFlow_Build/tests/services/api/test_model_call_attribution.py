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

- `test_every_model_port_caller_is_one_the_list_names` walks, for calls,
  **`OspreyFlow_Core/services` (every subfolder), `scripts`, `harness`, `cli` and `connectors`**,
  and, for files that import the model port, its gateway adapter or Laurium's, the same folders and
  **`OspreyFlow_Core/packages`** (all but the adapters that implement the port and the schemas and
  ports that declare it). A caller not in `REVIEWED_CALLERS` / `REVIEWED_FILES`, and an entry whose
  caller has gone, both fail.
- `test_every_route_that_reaches_a_model_caller_attributes_it` walks `services/api` and fails for a
  route that calls the question, extraction, email, document or ask-to-search service outside
  `model_calls.attributed(…)`.

Pure: no store, no network. The live stack owes: the gateway's own call
(`test_model_gateway_live.py` is the existing live case) and a real Postgres insert of the row (the
writer is the existing one, its insert proven by `test_audit_*` against Postgres).
"""

from __future__ import annotations

import ast
import asyncio
import json
import pathlib
import re
import secrets
import shutil
from collections.abc import Iterator
from contextlib import asynccontextmanager
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
SECRETS = {"key": KEY, "prompt": PROMPT, "address": ADDRESS}

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


def _routes(*, hosted_default: bool = False) -> ModelRoutes:
    gemini = Engine(
        name="gemini",
        label="Gemini",
        models={"extraction": "gemini/flash"},
        key_present=True,
        privacy_contract=True,
    )
    return ModelRoutes(
        locals=dict(LOCAL_MODELS),  # type: ignore[arg-type]
        engines={"gemini": gemini},
        defaults={"extraction": "gemini"} if hosted_default else {},
        sendable=frozenset({"P"}) if hosted_default else frozenset(),
    )


class _AnyDatasetMayGo:
    """ADR-136: every dataset allows a hosted engine."""

    async def egress_of(self, ids: Any) -> dict[str, Any]:
        from datetime import UTC, datetime

        from services.api.datasets import Dataset

        return {
            i: Dataset(
                id=i, name=i, owning_unit="unit-1", created_at=datetime(2026, 1, 1, tzinfo=UTC),
                created_by="x", egress="any",
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
        self, path: Scenario, *, hosted: bool = False, principal: Principal = ACTING
    ) -> None:
        self.path = path
        self.pool = _Pool()
        self.inner = _Inner(path.data())
        self.routed = RoutedModel(
            self.inner,  # type: ignore[arg-type]
            routes=_routes(hosted_default=hosted),
            egress=_AnyDatasetMayGo() if hosted else None,
        )
        self.principal = (
            principal if not hosted else principal.model_copy(update={"datasets": ["ds-1"]})
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

_METHODS = {"extract", "transcribe", "describe_image", "embed"}
_RECEIVER = re.compile(r"(^|[._])(model|inner|proposer|port|llm)$")
_PORT_IMPORTS = ("ports.model", "adapters.model_litellm", "adapters.extract_laurium")
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
        "the routing itself; no caller embeds today, and one that did would be recorded here",
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


def _imports_port(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(_PORT_IMPORTS):
                return True
        if isinstance(node, ast.Import):
            if any(a.name.startswith(_PORT_IMPORTS) for a in node.names):
                return True
    return False


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return node.id if isinstance(node, ast.Name) else "?"


def model_port_callers(core: pathlib.Path = CORE) -> tuple[set[tuple[str, str, str]], set[str]]:
    """(calls, files) found under `core`: every `<model-ish>.extract|transcribe|describe_image|
    embed(…)` in the call folders, with its enclosing function; every file importing the port."""
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

                def visit_Call(self, node: ast.Call) -> None:
                    f = node.func
                    if (isinstance(f, ast.Attribute) and f.attr in _METHODS
                            and _RECEIVER.search(_dotted(f.value))):  # fmt: skip
                        calls.add((rel, ".".join(self.stack), f"{_dotted(f.value)}.{f.attr}"))
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
    assert len(calls) >= 9 and len(files) >= 10
    assert {c[2] for c in calls} >= {"self._model.extract", "model.extract", "self._inner.embed"}


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
    that calls it under a name the receiver pattern does not know."""
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
        ("services/ingest/planted_summary.py", "Summary.summarise", "self._model.extract")
    }
    assert files - set(REVIEWED_FILES) == {"services/worker_planted.py"}


def test_a_listed_caller_that_has_gone_is_found(tmp_path: pathlib.Path) -> None:
    core = _copy_services(tmp_path)
    path = core / "services" / "api" / "pattern_ask.py"
    path.write_text(path.read_text().replace("self._model.extract(", "self._model.guess("))
    calls, _ = model_port_callers(core)
    assert ("services/api/pattern_ask.py", "PatternProposer.propose",
            "self._model.extract") not in calls  # fmt: skip


#: The services a route asks that reach the model, and the name each is held by in `app.py`.
_ENTRY_POINTS = {"questions.ask", "review_module.run_extraction", "email_extraction.extract",
                 "document_content.extract", "pattern_ask.ask"}  # fmt: skip
_ENTRY_OWNERS = {"questions", "review", "email_extraction", "document_content", "pattern_ask"}


def routes_outside_attribution(root: pathlib.Path = SERVICES / "api") -> list[str]:
    """Each function in `root` that calls an entry point other than inside a
    `async with model_calls.attributed(…)` block."""
    found: list[str] = []
    for path in sorted(root.glob("*.py")):
        if path.stem in _ENTRY_OWNERS:
            continue
        tree = ast.parse(path.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            guarded: set[int] = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.AsyncWith | ast.With) and any(
                    isinstance(i.context_expr, ast.Call)
                    and _dotted(i.context_expr.func) == "model_calls.attributed"
                    for i in node.items
                ):
                    guarded |= {id(n) for b in node.body for n in ast.walk(b)}
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and _dotted(node.func) in _ENTRY_POINTS
                        and id(node) not in guarded):  # fmt: skip
                    found.append(f"{path.name}:{node.lineno} {fn.name} calls {_dotted(node.func)}")
    return found


def test_every_route_that_reaches_a_model_caller_attributes_it() -> None:
    assert routes_outside_attribution() == []


def test_the_route_scan_finds_the_five_routes(tmp_path: pathlib.Path) -> None:
    """The scan sees what it claims: with every attribution made unrecognisable in a copy, it
    names the five routes, and no other."""
    root = tmp_path / "api"
    shutil.copytree(SERVICES / "api", root, ignore=shutil.ignore_patterns("__pycache__"))
    source = (root / "app.py").read_text()
    assert "model_calls.attributed(" in source
    (root / "app.py").write_text(source.replace("model_calls.attributed(", "unattributed("))
    named = sorted(f.split()[1] for f in routes_outside_attribution(root))
    assert named == ["ask_question_route", "ask_to_search_route", "extract_document_route",
                     "extract_email_route", "run_extraction_route"]  # fmt: skip


def test_a_route_that_stops_attributing_is_found(tmp_path: pathlib.Path) -> None:
    """Planted at the real site: `ask_question_route`'s own `async with` block, and nothing else,
    made into a plain call."""
    root = tmp_path / "api"
    shutil.copytree(SERVICES / "api", root, ignore=shutil.ignore_patterns("__pycache__"))
    source = (root / "app.py").read_text()
    head, _, rest = source.partition("async def ask_question_route(")
    body, sep, tail = rest.partition("\n\n\n@app.")
    assert "model_calls.attributed(" in body, "ask_question_route does not attribute"
    (root / "app.py").write_text(
        head
        + "async def ask_question_route("
        + body.replace("model_calls.attributed(", "unattributed(")
        + sep
        + tail
    )
    found = routes_outside_attribution(root)
    assert len(found) == 1 and "ask_question_route calls questions.ask" in found[0]
