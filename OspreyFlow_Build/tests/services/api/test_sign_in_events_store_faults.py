"""SE8c, round 7: a write that fails in a way the audit writer does not name still leaves no session
unrecorded (rule 12; `RULINGS.md` SE8: the design over-records and never under-records).

`AuditWriter.record` wraps `OSError` and `asyncpg.PostgresError` in `AuditWriteError`, and nothing
else. A pool that is closing (a replica stopping in a rolling restart) raises asyncpg's
`InterfaceError`, which is neither, and a request cancelled in the middle of the write raises
`CancelledError`. `SignInWatch` had put its "seen" mark in Valkey before the write and cleared it
only for an `AuditWriteError`, so for any other failure the mark stayed for twelve hours and no
replica wrote that session's row; for a report, the retry was answered `recorded: false` with no row
ever written.

**Rule 15: the faults take the shape the real writer lets through.** The failure is raised from the
audit pool's own `execute`, the same place the real driver raises it, so it passes through the real
`AuditWriter.record` exactly as the real one does (not an exception planted above it), and the
exceptions are the driver's own class (`asyncpg.InterfaceError('pool is closing')`) and asyncio's own
`CancelledError`, which `AuditWriter` does not wrap.

Reuses the rig of `test_sign_in_events.py` (the real app, resolver and writer over stand-ins that
refuse what the real stores refuse).

**Folders walked:** none. Everything is run, not read.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from schemas.domain import Principal
from services.api import audit as audit_module

from tests.services.api import test_sign_in_events as base
from tests.services.api.test_sign_in_events import (  # noqa: F401 - fixtures, found by name
    Rig,
    mod,
    rig,
)


def _fail_with(monkeypatch: pytest.MonkeyPatch, rig_: Rig, make: Any) -> dict[str, bool]:
    """The audit pool's insert fails with `make()` while `state['on']`: raised from `execute`, under
    the real `AuditWriter.record`."""
    state = {"on": True}
    real = base._Conn.execute

    async def execute(self: Any, sql: str, *args: Any) -> None:
        if state["on"]:
            raise make()
        await real(self, sql, *args)

    monkeypatch.setattr(base._Conn, "execute", execute)
    return state


def _closing() -> BaseException:
    return audit_module.asyncpg.InterfaceError("pool is closing")


def test_the_pool_closing_leaves_a_first_sight_to_be_written_by_the_next_request(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    s = rig.session()
    token = s.token()
    state = _fail_with(monkeypatch, rig, _closing)
    assert rig.me(token).status_code == 200, "the request is answered: a record's fault locks no one"
    assert rig.pool.rows == [] and rig.watch.misses == 1
    assert [k for k in rig.valkey.data if k.startswith("sign-in-events:seen:")] == [], (
        "the mark that says 'seen' is cleared, in Valkey, where every replica reads it"
    )
    state["on"] = False
    # Another replica, which holds nothing in its own memory: only Valkey's mark can stop it.
    rig.use(rig.replica())
    assert rig.me(token).status_code == 200
    assert rig.me(token).status_code == 200
    assert len(rig.pool.of("sign_in_seen")) == 1
    assert base.leaks(rig, caplog, base.forbidden(token, rig, s, {})) == []


def test_the_same_replica_writes_it_at_the_next_request_too(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = rig.session()
    token = s.token()
    state = _fail_with(monkeypatch, rig, _closing)
    rig.me(token)
    state["on"] = False
    rig.me(token)
    rig.me(token)
    assert len(rig.pool.of("sign_in_seen")) == 1


def test_a_request_cancelled_in_the_write_leaves_the_session_to_be_seen_again(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = rig.session()
    token = s.token()
    state = _fail_with(monkeypatch, rig, asyncio.CancelledError)
    principal = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rig.watch.note_seen(token, principal))
    assert [k for k in rig.valkey.data if k.startswith("sign-in-events:seen:")] == []
    state["on"] = False
    rig.use(rig.replica())
    assert rig.me(token).status_code == 200
    assert len(rig.pool.of("sign_in_seen")) == 1


def test_the_route_answers_503_for_a_closing_pool_and_the_retry_records_once(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    s = rig.session()
    token = s.token()
    state = _fail_with(monkeypatch, rig, _closing)
    answer = rig.event(token, "sign_in")
    assert answer.status_code == 503 and answer.json()["error"] == "audit_unavailable", (
        answer.status_code,
        answer.text,
    )
    assert rig.pool.of("sign_in") == []
    assert [k for k in rig.valkey.data if k.startswith("sign-in-events:sign_in:")] == [], (
        "the report's mark is cleared, so the retry is not taken for a repeat"
    )
    state["on"] = False
    assert rig.event(token, "sign_in").json() == {"recorded": True}
    assert rig.event(token, "sign_in").json() == {"recorded": False}
    assert len(rig.pool.of("sign_in")) == 1
    assert base.leaks(rig, caplog, base.forbidden(token, rig, s, {})) == []


def test_a_report_cancelled_in_the_write_is_recorded_when_sent_again(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = rig.session()
    token = s.token()
    state = _fail_with(monkeypatch, rig, asyncio.CancelledError)
    principal = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rig.watch.record_event(token, principal, "sign_out"))
    state["on"] = False
    assert rig.event(token, "sign_out").json() == {"recorded": True}
    assert len(rig.pool.of("sign_out")) == 1


def test_the_miss_is_loud_and_names_no_word_of_the_driver(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _fail_with(monkeypatch, rig, _closing)
    rig.me(rig.session().token())
    text = base.logged(caplog)
    assert "sign-in record" in text and "InterfaceError" in text
    assert "pool is closing" not in text, "a driver's own words can hold an address"
