"""L2.8c's carry (c), ADR-109 Amendment 12: a revert's removal from the working sets
(`WorkingSetReverter.remove`) and an alert's purge (`alerts.purge_copies`) are one removal,
`working_set_revert.remove_and_publish`, so the two cannot drift apart (each had its own copy of
"remove from every case, then publish each case's removal"). The behaviour against the real stores
is `tests/ingest/test_repoint_journal_callers_live.py`'s published purge and the revert's own tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from services.api import alerts as alerts_module
from services.api import working_set_revert
from services.api.working_set_revert import WorkingSetReverter, remove_and_publish


class _Service:
    """`WorkingSetService.remove_reverted`: two cases held a copy."""

    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.publisher: Any = None

    async def remove_reverted(self, nodes: Any, links: Any) -> list[Any]:
        self._events.append(f"removed {sorted(nodes)} {sorted(links)}")
        return [
            SimpleNamespace(investigation_id="case-a", delta={"op": "remove", "case": "a"}),
            SimpleNamespace(investigation_id="case-b", delta={"op": "remove", "case": "b"}),
        ]


async def test_every_store_is_cleared_before_anything_is_published_and_each_case_on_its_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The removal's order and channels: `remove_reverted` clears every case's store before it
    returns, and only then is anything published (a socket resynchronising on a published message
    finds the stores already clean), each case's removal on that case's own channel. Red with every
    removal published on the first case's channel: case b's canvas was never told."""
    events: list[str] = []

    async def publish(client: Any, case: str, delta: Any) -> None:
        events.append(f"published {case}")

    monkeypatch.setattr(working_set_revert, "publish_delta", publish)
    removals = await remove_and_publish(_Service(events), object(), ["n1"], ["e1"])
    assert events == ["removed ['n1'] ['e1']", "published case-a", "published case-b"]
    assert [r.investigation_id for r in removals] == ["case-a", "case-b"]


async def test_a_service_built_without_a_client_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A test's service has no client: the stores are cleared and nothing is published."""
    events: list[str] = []

    async def publish(client: Any, case: str, delta: Any) -> None:
        events.append(f"published {case}")

    monkeypatch.setattr(working_set_revert, "publish_delta", publish)
    await remove_and_publish(_Service(events), None, ["n1"], [])
    assert events == ["removed ['n1'] []"]


async def test_the_revert_and_the_alerts_purge_both_remove_through_the_one_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both callers reach `remove_and_publish`: the revert with its Valkey client and the links it
    took back, the alert purge with the service's own publisher and nodes alone. Red with either
    keeping its own copy of the removal: that caller never reached the helper."""
    calls: list[tuple[str, Any, list[str], list[str]]] = []

    async def recorded(service: Any, publisher: Any, nodes: Any, links: Any) -> list[Any]:
        calls.append((type(service).__name__, publisher, list(nodes), list(links)))
        return []

    class _History:
        async def remove_elements(self, nodes: Any, links: Any) -> int:
            return 0

    monkeypatch.setattr(working_set_revert, "remove_and_publish", recorded)
    service, valkey = _Service([]), object()
    service.publisher = object()
    await WorkingSetReverter(service, valkey, _History()).remove(["n1"], ["e1"])  # type: ignore[arg-type]
    await alerts_module.purge_copies(service, ["alert-node-1"])
    assert calls == [
        ("_Service", valkey, ["n1"], ["e1"]),
        ("_Service", service.publisher, ["alert-node-1"], []),
    ]
