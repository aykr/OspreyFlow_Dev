"""Phase 9's API and JSON connectors, offline (`06_DECISIONS.md` ADR-140 Amendment 13; the
redesign's phase 9). The telco-lookup API is a synthetic fixture (rule 9): an
`httpx.MockTransport` that refuses what a real API refuses (rule 15: a missing or wrong bearer
token, an unknown path, a server error), not only what it grants.

What a mistake would do, and the case that catches it:
- a host off the deployment's egress allow-list reached —
  `test_a_host_off_the_allow_list_is_never_reached`;
- the secret's value sent without being asked for, or a refusal read as an empty page —
  `test_the_api_s_refusals_are_refused_in_words_never_read_as_no_rows`;
- pages after the first dropped, or a next link followed off the host —
  `test_every_page_is_read`, `test_a_next_link_off_the_host_is_refused`;
- more rows than a read may hold cut short silently (rule 2) —
  `test_a_read_past_the_cap_is_refused_whole`;
- a JSON record's nested value lost, or records read from the wrong place —
  `test_json_files_are_read_at_their_records_path`;
- a snapshot written where a pipeline cannot find it, or half-written as a run reads it —
  `test_a_read_lands_whole_as_the_source_s_one_file`.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from services.ingest.connectors import reads
from services.ingest.connectors.reads import (
    ConnectorRefused,
    read_api,
    read_json,
    write_snapshot,
)

from schemas.sources import ApiConnectionSettings, ApiRead, JsonRead

TOKEN = "synthetic-token-123"
NUMBERS = [
    {"number": "07700900001", "network": "Synthetic Mobile", "owner": {"name": "SYN-OWNER-1"}},
    {"number": "07700900002", "network": "Synthetic Mobile", "owner": None},
    {"number": "07700900003", "network": "Fictional Telecom", "ported": True},
]


def _telco(request: httpx.Request) -> httpx.Response:
    """The synthetic telco lookup: bearer only, paged by `page`, two records a page."""
    if request.headers.get("authorization") != f"Bearer {TOKEN}":
        return httpx.Response(401, json={"error": "unauthorised"})
    if request.url.path == "/v1/broken":
        return httpx.Response(503, text="maintenance")
    if request.url.path != "/v1/numbers":
        return httpx.Response(404, json={"error": "not found"})
    page = int(request.url.params.get("page", "1"))
    chunk = NUMBERS[(page - 1) * 2 : page * 2]
    return httpx.Response(200, json={"data": {"items": chunk}})


def _linked(request: httpx.Request) -> httpx.Response:
    cursor = request.url.params.get("after")
    if cursor is None:
        return httpx.Response(200, json={"items": NUMBERS[:2],
                                         "next": "https://telco.example/v1/n?after=2"})  # fmt: skip
    return httpx.Response(200, json={"items": NUMBERS[2:], "next": None})


API = ApiConnectionSettings(base_url="https://telco.example", auth="bearer", secret="TELCO",
                            pagination="page")  # fmt: skip
READ = ApiRead(path="/v1/numbers", records_at="data.items")


async def _read(
    settings: ApiConnectionSettings = API, read: ApiRead = READ, **kw: object
) -> object:
    handler = kw.pop("handler", _telco)
    return await read_api(
        settings, read, secret=kw.pop("secret", TOKEN),
        allowed_hosts=kw.pop("hosts", ["telco.example"]), transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )  # fmt: skip


async def test_every_page_is_read() -> None:
    got = await _read()
    assert [r["number"] for r in got.rows] == [n["number"] for n in NUMBERS]  # type: ignore[attr-defined]
    assert got.columns == ["number", "network", "owner", "ported"]  # type: ignore[attr-defined]
    assert got.rows[0]["owner"] == '{"name":"SYN-OWNER-1"}'  # type: ignore[attr-defined]
    assert got.rows[1]["owner"] is None and got.rows[2]["ported"] == "true"  # type: ignore[attr-defined]


async def test_a_host_off_the_allow_list_is_never_reached() -> None:
    seen: list[httpx.Request] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _telco(request)

    with pytest.raises(ConnectorRefused, match="egress allow-list") as refused:
        await _read(hosts=["other.example"], handler=spy)
    assert seen == []
    assert "telco.example" in str(refused.value)


@pytest.mark.parametrize(
    ("secret", "read", "words"),
    [
        ("wrong", READ, "refused the sign-in"),
        (TOKEN, ApiRead(path="/v1/nothing-here", records_at="data.items"), "404"),
        (TOKEN, ApiRead(path="/v1/broken"), "503"),
    ],
)
async def test_the_api_s_refusals_are_refused_in_words_never_read_as_no_rows(
    secret: str, read: ApiRead, words: str
) -> None:
    with pytest.raises(ConnectorRefused, match=words) as refused:
        await _read(read=read, secret=secret)
    assert TOKEN not in str(refused.value) and "wrong" not in str(refused.value)


async def test_records_not_found_at_their_path_are_refused() -> None:
    with pytest.raises(ConnectorRefused, match="records"):
        await _read(read=ApiRead(path="/v1/numbers", records_at="data.rows"))


async def test_a_next_link_off_the_host_is_refused() -> None:
    linked = ApiConnectionSettings(base_url="https://telco.example", pagination="next_link",
                                   next_at="next")  # fmt: skip
    got = await _read(linked, ApiRead(path="/v1/n", records_at="items"), handler=_linked)
    assert len(got.rows) == 3  # type: ignore[attr-defined]

    def elsewhere(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [], "next": "https://evil.example/steal"})

    with pytest.raises(ConnectorRefused, match="another host"):
        await _read(linked, ApiRead(path="/v1/n", records_at="items"), handler=elsewhere)


async def test_a_read_past_the_cap_is_refused_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reads, "MAX_ROWS", 2)
    with pytest.raises(ConnectorRefused, match="more than 2 rows"):
        await _read()


def test_json_files_are_read_at_their_records_path() -> None:
    doc = {"meta": {"v": 1}, "records": [{"booking_id": 1, "visitor": {"ref": "V-1"}},
                                          {"booking_id": 2, "slots": [1, 2]}]}  # fmt: skip
    got = read_json([("bookings-1.json", json.dumps(doc).encode())],
                    JsonRead(pattern="bookings-*.json", records_at="records"))  # fmt: skip
    assert got.rows == [
        {"booking_id": "1", "visitor": '{"ref":"V-1"}', "slots": None},
        {"booking_id": "2", "visitor": None, "slots": "[1,2]"},
    ]
    with pytest.raises(ConnectorRefused, match="bookings-2.json"):
        read_json([("bookings-2.json", b"{not json")], JsonRead(pattern="*.json"))
    with pytest.raises(ConnectorRefused, match="a list of records"):
        read_json([("b.json", b'{"records": 3}')], JsonRead(pattern="*.json", records_at="records"))


def test_a_read_lands_whole_as_the_source_s_one_file(tmp_path: Path) -> None:
    rows = reads.ReadRows(columns=["a", "b"], rows=[{"a": "1", "b": None}, {"a": "2", "b": "x"}])
    path = write_snapshot(rows, tmp_path / "uploaded" / "ds-a", "visit_bookings")
    assert path == tmp_path / "uploaded" / "ds-a" / "visit_bookings.csv"
    assert path.read_text() == "a,b\n1,\n2,x\n"
    assert [p.name for p in path.parent.iterdir()] == ["visit_bookings.csv"]
    write_snapshot(reads.ReadRows(columns=["a", "b"], rows=[]), path.parent, "visit_bookings")
    assert path.read_text() == "a,b\n"
