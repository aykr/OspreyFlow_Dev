"""Every model call is recorded with who asked, for which case, and which engine and model
answered (SE8a; `RULINGS.md` SE8: "every model call recorded with who asked, for which case and to
which engine, in one record"; `03_CONDUIT_MIDDLEWARE.md` §6).

**How.** A route that reaches a model asks it inside `attributed(audit, principal, case, job=…,
via=…)`. The routing (`model_routing.RoutedModel`) notes each call it makes in that block, with the
engine and model *it chose for the call* (`note`; the engine registry's own record of the target,
never the request's), and the block's exit writes one `model_call` row per noted call, through the
audit writer every other row uses. A call made outside any block (no person, no case) notes
nothing; the scan in `tests/services/api/test_model_call_attribution.py` fails for a route that
reaches a model outside one, and for a caller of the port it does not name.

**What a row holds**, in `resolved_query` (no new column: `audit_log` is written by every route and
a column added to it takes `ACCESS EXCLUSIVE` on a table whose write failing refuses the read it
audits; the field already holds each action's own detail): `job` (ask, extract, email, transcribe,
describe, embed, pattern_ask), `engine` and `model` (null for a call refused before any engine was
chosen), `outcome` (answered, refused, errored, interrupted) and `via` (the action of the route's
own row). The person, the case and the unit are the row's own columns. **Names only:** a call is
noted as `ModelCall`, whose four fields are all there is to write; there is no place in it for a
prompt, an answer, a document's text, a key, a token, an engine's address or an error's words.

**Fail closed.** A row that cannot be written raises `AuditWriteError` (503), as every audit write
does, so no answer reaches a person whose call was not recorded. A refused or failed call is
recorded before the refusal or failure goes on to be said in words, unchanged. A call cancelled
(the person closes the page) is recorded as interrupted: the write is shielded from the cancel.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Literal

from schemas.domain import Principal

from .audit import AuditWriter

Outcome = Literal["answered", "refused", "errored", "interrupted"]

#: The audit action of a model call's row (classified in `audit_section.READS_AND_OTHER`).
ACTION = "model_call"

#: What an extraction-role call is filed under until the route says what it is for (ask, email, …).
EXTRACT = "extract"


@dataclass(frozen=True)
class ModelCall:
    """One call, by name alone. `engine` and `model` are `None` for a call refused before the
    routing chose an engine."""

    job: str
    engine: str | None
    model: str | None
    outcome: Outcome


@dataclass
class _Ledger:
    #: What the route's extraction-role calls are for.
    job: str
    calls: list[ModelCall]


_current: contextvars.ContextVar[_Ledger | None] = contextvars.ContextVar(
    "osprey_model_call_ledger", default=None
)


def note(call: ModelCall) -> None:
    """The routing's record of one call, for the block it was made in; nothing if made in none."""
    ledger = _current.get()
    if ledger is None:
        return
    job = ledger.job if call.job == EXTRACT else call.job
    ledger.calls.append(replace(call, job=job))


async def _write(
    audit: AuditWriter,
    principal: Principal,
    investigation_id: str | None,
    via: str,
    calls: list[ModelCall],
) -> None:
    for call in calls:
        await audit.record(
            principal=principal,
            action=ACTION,
            investigation_id=investigation_id,
            resolved_query={
                "job": call.job,
                "engine": call.engine,
                "model": call.model,
                "outcome": call.outcome,
                "via": via,
            },
            result_cardinality=1 if call.outcome == "answered" else 0,
        )


@asynccontextmanager
async def attributed(
    audit: AuditWriter,
    principal: Principal,
    investigation_id: str | None,
    *,
    job: str,
    via: str,
) -> AsyncIterator[None]:
    """Model calls made inside are recorded, one row each, when the block ends, however it ends.
    `job` is what the route's extraction calls are for; `via` is the action of the route's own row.
    """
    ledger = _Ledger(job, [])
    token = _current.set(ledger)
    try:
        yield
    finally:
        _current.reset(token)
        if ledger.calls:
            # Shielded: a cancelled request still has its calls written, and a write that fails
            # fails closed in the ordinary way.
            writing = asyncio.ensure_future(
                _write(audit, principal, investigation_id, via, ledger.calls)
            )
            await asyncio.shield(writing)
