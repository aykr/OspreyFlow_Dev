"""ADR-110 Amendment 18: a correction of a link whose id two edge types hold is refused in words,
never a 500, and writes nothing. `supersede_edge` raises `AmbiguousLinkId` rather than marking
every type's link superseded. The link-change service rolls its transaction back and records
nothing, and every route answers it alike: 409 `link_id_ambiguous`, words naming no type and no
other link (rule 3). The handler is the app's own, so the link change, a picture's change and an
alert's close all answer the same. Red with the handler removed
(`process/lanes/studio/L1.2a_RED_RECORD.md`)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from ports.graph import AmbiguousLinkId
from services.api.link_changes import LinkChangeRequest

from tests.services.api.test_link_change_routes import URL, client  # noqa: F401 (the fixture)
from tests.services.api.test_link_changes import ANALYST, _build


async def test_the_service_writes_nothing_for_an_ambiguous_id() -> None:
    service, graph, store, changes, notes = await _build()
    graph.fail_with = AmbiguousLinkId("e1", ["COMMUNICATED_WITH", "TRANSACTED"])

    with pytest.raises(AmbiguousLinkId):
        await service.change("inv-1", "e1", ANALYST, LinkChangeRequest(type="FAMILY_OF", reason="r"))

    assert await store.get_edge("inv-1", "e1") is not None
    assert changes.rows == [] and notes.moves == []


def test_the_route_answers_an_ambiguous_id_in_words_and_publishes_nothing(
    client: TestClient,  # noqa: F811
) -> None:
    client.service.error = AmbiguousLinkId("e1", ["COMMUNICATED_WITH", "TRANSACTED"])  # type: ignore[attr-defined]

    response = client.post(f"{URL}/change", json={"type": "FAMILY_OF", "reason": "r"})

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "link_id_ambiguous"
    assert "nothing was written" in body["detail"]
    assert "TRANSACTED" not in response.text and "COMMUNICATED_WITH" not in response.text
    assert client.valkey.published == []  # type: ignore[attr-defined]
    assert client.audit.records == []  # type: ignore[attr-defined]
