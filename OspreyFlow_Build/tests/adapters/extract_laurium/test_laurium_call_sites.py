"""Only the review queue's route reaches Laurium (`06_DECISIONS.md` ADR-135 Amendment 9 point 2; the
orchestrator's round 1 on P12 part 2, its blocker): `run_extraction` is also how email extraction
(`EmailExtractionService.extract(using="model")`) and a document's content
(`DocumentContentService.extract(using="model")`) extract, so the marker is no longer set inside it;
`run_extraction(laurium_may_read=True)` is passed by the review queue's route alone.

At the email and document call sites, in their real call shape (each service's own `extract`, built
as its own tests build it, its model a `LauriumExtracts` over the same two engines; the Conduit's own
composition is `routed_model`'s, tested in `test_laurium_start.py`): **Deep read is asked and Laurium
is not.** And no module under `services/` or `packages/` may pass the flag or set the marker but the
two sanctioned sites (the review queue's route, and `run_extraction` itself), read from every module.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any

from adapters.extract_laurium.composed import LauriumExtracts
from schemas.model import ExtractionRequest, ExtractionResult


class _Laurium:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.asked.append(req.document_id)
        return ExtractionResult(document_id=req.document_id, model=req.model, data=json.loads("{}"))


def _composed(service: Any) -> _Laurium:
    laurium = _Laurium()
    service._model = LauriumExtracts(service._model, laurium)  # type: ignore[arg-type]  # noqa: SLF001
    return laurium


async def test_email_extraction_by_the_model_reaches_deep_read_not_laurium() -> None:
    from tests.services.api.test_email_extraction import ANALYST, TEXT, _build

    service, _, _, _, model = await _build()
    laurium = _composed(service)
    await service.extract("inv-1", "e1", "ev-1", ANALYST, using="model")
    assert [r.text for r in model.requests] == [TEXT]
    assert laurium.asked == []


async def test_a_documents_content_by_the_model_reaches_deep_read_not_laurium() -> None:
    from tests.services.api.test_document_content import ANALYST, _service

    service, _, _, _, _, _ = await _service()
    deep_read, laurium = _Laurium(), _Laurium()  # a recorder each; its media model has no extract
    service._model = LauriumExtracts(deep_read, laurium)  # type: ignore[arg-type]  # noqa: SLF001
    await service.extract("inv-1", "text-1", ANALYST, using="model")
    assert deep_read.asked == ["text-1"]
    assert laurium.asked == []


#: What may reach Laurium, read from every module's syntax tree (round 3, item 2): each keyword
#: argument `laurium_may_read=` given at a call, each import or call of `laurium_reads` under any
#: name, and each assignment to `_LAURIUM_READS` outside its own module. The parameter's own default in
#: `run_extraction`'s signature is not a call and is not counted.
SANCTIONED = {
    ("services/api/app.py", "laurium_may_read="): 1,  # run_extraction_route's call, True
    ("services/api/review.py", "laurium_reads"): 2,  # its import, and its one use behind the flag
    ("packages/adapters/extract_laurium/composed.py", "laurium_reads"): 1,  # its definition
    (
        "packages/adapters/extract_laurium/composed.py",
        "_LAURIUM_READS=",
    ): 1,  # the ContextVar itself
}
CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"


def _uses(tree: ast.AST) -> dict[str, int]:
    counts: dict[str, int] = {}
    aliases = {"laurium_reads"}

    def add(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                if name.name == "laurium_reads":
                    aliases.add(name.asname or name.name)
                    add("laurium_reads")
                if name.name == "_LAURIUM_READS":
                    add("_LAURIUM_READS=")
        elif (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == "laurium_reads"
        ):
            add("laurium_reads")
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "_LAURIUM_READS" for t in targets):
                add("_LAURIUM_READS=")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "laurium_may_read":
                    add("laurium_may_read=")
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name in aliases:
                add("laurium_reads")
    return counts


def _found() -> dict[tuple[str, str], int]:
    found: dict[tuple[str, str], int] = {}
    for root in ("services", "packages"):
        for path in sorted((CORE / root).rglob("*.py")):
            if ".venv" in path.parts or "node_modules" in path.parts:
                continue
            for key, count in _uses(ast.parse(path.read_text("utf-8"))).items():
                found[(str(path.relative_to(CORE)), key)] = count
    return found


def test_only_the_sanctioned_sites_reach_laurium() -> None:
    assert _found() == SANCTIONED


def test_the_route_that_passes_it_is_the_review_queues() -> None:
    from services.api import app as app_module

    assert "laurium_may_read=True" in inspect.getsource(app_module.run_extraction_route)
