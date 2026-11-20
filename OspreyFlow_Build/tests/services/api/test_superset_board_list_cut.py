"""SE4 item 3 (rule 2): the board list is never cut at 100 without saying so.

`SupersetEmbedder.dashboards` asked Superset for one page of 100 (`page_size:100`) and never read the
count or a next page, so a deployment with 101 registered dashboards listed 100 and said nothing.

The fake Superset here honours `page` and `page_size` as Superset's own list API does (rison in `q`,
`count` the total), and holds 101 registered dashboards: the existing fake in test_superset_embed.py
ignores both and never returns more than three. The route is asked, not the helper. It answers all
101, or a typed refusal naming the limit; never exactly 100 with a success.

Rule 15: a fake models the real dependency's refusals as well as its grants. This one refuses a page
size above Superset's own maximum (a request for more than it will give is answered with 400, as
Superset's `FAB_API_MAX_PAGE_SIZE` does), and a page past the last answers an empty result.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_identity_admin,
    get_investigations,
    get_principal,
    get_superset_embedder,
)
from services.api.investigations import AccessLevel, Investigation
from services.api.superset_embed import SupersetEmbedder, SupersetSettings

from ontology.handling import load_uk_le_scheme
from schemas.admin import DashboardIdentity
from schemas.domain import Principal

VIEWER = Principal(id="u-viewer", clearance="OFFICIAL", org_unit="verify", roles=["reports_viewer"])
#: Superset's own maximum page size (`FAB_API_MAX_PAGE_SIZE`'s default).
SUPERSET_MAX_PAGE = 100


def _identity(n: int) -> DashboardIdentity:
    return DashboardIdentity(
        client_id=f"osprey-dashboard-board-{n:03d}", account_id=f"sa-board-{n:03d}",
        clearance="OFFICIAL", org_unit="verify",
    )  # fmt: skip


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return []


class _Identities:
    def __init__(self, count: int) -> None:
        self.count = count

    async def list_dashboards(self) -> list[DashboardIdentity]:
        return [_identity(n) for n in range(self.count)]


class _Names:
    async def display_names(self, ids):  # type: ignore[no-untyped-def]
        return {}


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


class _Superset:
    """Superset's dashboard list as it answers: paged by `q=(page:N,page_size:M)`, `count` the total."""

    def __init__(self, registered: int) -> None:
        self.dashboards = [
            {"id": n + 1, "slug": f"board-{n:03d}", "dashboard_title": f"Board {n:03d}"}
            for n in range(registered)
        ]
        self.list_calls: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/security/login":
            return httpx.Response(200, json={"access_token": "jwt"})
        if request.headers.get("Authorization") != "Bearer jwt":
            return httpx.Response(401, json={"msg": "Missing Authorization Header"})
        if path == "/api/v1/security/csrf_token/":
            return httpx.Response(200, json={"result": "csrf"})
        if path == "/api/v1/dashboard/":
            q = request.url.params.get("q", "")
            self.list_calls.append(q)
            page = int((re.search(r"page:(\d+)", q) or [0, 0])[1])
            size = int((re.search(r"page_size:(\d+)", q) or [0, 20])[1])
            if size > SUPERSET_MAX_PAGE:
                return httpx.Response(400, json={"message": "page_size too large"})
            chunk = self.dashboards[page * size : (page + 1) * size]
            return httpx.Response(200, json={"count": len(self.dashboards), "result": chunk})
        return httpx.Response(404, json={"message": "Not found"})


def _client(registered: int, *, identities: int | None = None) -> tuple[TestClient, _Superset]:
    superset = _Superset(registered)
    settings = SupersetSettings(
        "http://superset:8088", "http://localhost:8088", "http://localhost:8080", "right"
    )
    embedder = SupersetEmbedder(settings, transport=httpx.MockTransport(superset.handle))
    names = registered if identities is None else identities
    app.dependency_overrides.update({
        get_principal: lambda: VIEWER, get_superset_embedder: lambda: embedder,
        get_identity_admin: lambda: _Identities(names), get_investigations: _Cases,
        get_handling_scheme: load_uk_le_scheme, get_audit: _Audit,
    })  # fmt: skip
    return TestClient(app, raise_server_exceptions=False), superset


@pytest.fixture(autouse=True)
def _clear():  # type: ignore[no-untyped-def]
    yield
    app.dependency_overrides.clear()


def test_a_hundred_and_one_registered_boards_are_never_quietly_cut_to_a_hundred() -> None:
    client, _ = _client(101)
    answer = client.get("/v1/reports/dashboards")
    if answer.status_code == 200:
        slugs = [b["slug"] for b in answer.json()]
        assert len(slugs) != 100, "the list stopped at 100 and said nothing (rule 2)"
        assert len(slugs) == 101 and len(set(slugs)) == 101, "a success must hold every board"
    else:
        body = answer.json()
        assert answer.status_code in (413, 422, 502), answer.text
        assert isinstance(body.get("error"), str) and body["error"], "a typed refusal"
        assert "100" in body["detail"] or "limit" in body["detail"].lower(), body


def test_every_board_is_listed_by_reading_the_pages_to_the_count() -> None:
    """The shape this build chose: every board, the pages read to the count Superset reports."""
    client, superset = _client(101)
    answer = client.get("/v1/reports/dashboards")
    assert answer.status_code == 200, answer.text
    assert [b["slug"] for b in answer.json()] == [f"board-{n:03d}" for n in range(101)]
    assert len(superset.list_calls) >= 2, "one page cannot hold 101"


def test_the_last_board_of_many_pages_is_listed() -> None:
    client, _ = _client(250)
    answer = client.get("/v1/reports/dashboards")
    assert answer.status_code == 200, answer.text
    assert len(answer.json()) == 250
    assert answer.json()[-1]["slug"] == "board-249"


def test_a_list_that_cannot_be_read_whole_is_said_not_cut() -> None:
    """A Superset that reports 101 but never gives a second page (one that ignores `page`): the
    route says so in words rather than answering what it has."""
    client, superset = _client(101)

    def stuck(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/dashboard/":
            first = superset.dashboards[:100]
            return httpx.Response(200, json={"count": 101, "result": first})
        return superset.handle(request)

    embedder = SupersetEmbedder(
        SupersetSettings(
            "http://superset:8088", "http://localhost:8088", "http://localhost:8080", "right"
        ),
        transport=httpx.MockTransport(stuck),
    )
    app.dependency_overrides[get_superset_embedder] = lambda: embedder
    answer = client.get("/v1/reports/dashboards")
    assert answer.status_code == 502, answer.text
    assert answer.json()["error"] == "superset_refused"
    assert "101" in answer.json()["detail"]


# --- Controls (rule 15) ---------------------------------------------------------------------------


def test_with_three_boards_nothing_changes() -> None:
    client, _ = _client(3)
    answer = client.get("/v1/reports/dashboards")
    assert answer.status_code == 200, answer.text
    assert answer.json() == [
        {"slug": f"board-{n:03d}", "title": f"Board {n:03d}"} for n in range(3)
    ]


def test_exactly_a_hundred_boards_are_a_hundred() -> None:
    client, _ = _client(100)
    answer = client.get("/v1/reports/dashboards")
    assert answer.status_code == 200, answer.text
    assert len(answer.json()) == 100


def test_the_fake_refuses_what_superset_refuses() -> None:
    """The fake is not more permissive than the dependency: a page size above Superset's maximum is
    refused, so a fix that asks for one big page cannot pass by it."""
    superset = _Superset(101)
    refused = superset.handle(httpx.Request(
        "GET", "http://superset:8088/api/v1/dashboard/", params={"q": "(page_size:500)"},
        headers={"Authorization": "Bearer jwt"},
    ))  # fmt: skip
    assert refused.status_code == 400
    assert json.loads(refused.content)["message"]


def test_a_board_that_is_not_opened_to_the_viewer_is_still_not_listed() -> None:
    """Rule 4 beside the paging: boards past the first page are held to the same opening rule."""
    client, _ = _client(101, identities=50)
    answer = client.get("/v1/reports/dashboards")
    assert answer.status_code == 200, answer.text
    assert len(answer.json()) == 50
    assert all(int(b["slug"].rsplit("-", 1)[1]) < 50 for b in answer.json())
