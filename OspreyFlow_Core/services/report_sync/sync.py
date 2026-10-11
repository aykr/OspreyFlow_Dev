"""One sync pass (`06_DECISIONS.md` ADR-111 Amendment 2): for each configured dashboard identity,
discover the cases it has been granted, pull each case's feed as that identity, and write the mart.

**Every pull is a reader's read.** The dashboard signs in by the client-credentials grant and the
Conduit counts its figures as that identity (rule 3), audits the read and records it in the export
ledger; the mart holds only what that identity may see. The token is renewed before it expires; a
refused token is a failure said in words, the rows left with their last good pull — never refreshed
from anywhere else. **One pull per slot across every instance:** each (dashboard, case, slot) is
claimed with Valkey `SET NX`, as the KYC sweep claims its day. A dashboard no longer configured is
pruned from the mart.

The feed is pulled as CSV — the flat rows the Conduit's own `reports.feed_rows` produces — so the
mart cannot disagree with the Reports view.
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from valkey.asyncio import Valkey

from .mart import FigureRow, Mart


class SyncRefused(Exception):
    """The identity provider or the Conduit refused the dashboard; said in words."""


@dataclass
class Dashboard:
    client_id: str
    secret: str
    token_url: str
    conduit_url: str
    weeks: int = 12


@dataclass
class Summary:
    pulled: int = 0
    failed: int = 0
    skipped: int = 0
    changed: int = 0
    failures: list[str] = field(default_factory=list)


class TokenSource:
    """A dashboard's access token, renewed `margin_seconds` before it expires."""

    def __init__(self, token_url: str, client_id: str, secret: str, *, margin_seconds: float = 30.0,
                 clock: Callable[[], float] = time.monotonic) -> None:  # fmt: skip
        self._url, self._client_id, self._secret = token_url, client_id, secret
        self._margin, self._clock = margin_seconds, clock
        self._token: str | None = None
        self._expires = 0.0
        self._http = httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self) -> str:
        if self._token is not None and self._clock() < self._expires - self._margin:
            return self._token
        try:
            response = await self._http.post(
                self._url,
                data={"grant_type": "client_credentials", "client_id": self._client_id,
                      "client_secret": self._secret},
            )  # fmt: skip
        except httpx.HTTPError as e:
            raise SyncRefused(f"the identity provider could not be reached: {e}") from e
        if response.status_code != 200:
            raise SyncRefused(
                f"the identity provider refused {self._client_id} ({response.status_code})"
            )
        body = response.json()
        self._token = str(body["access_token"])
        self._expires = self._clock() + float(body.get("expires_in", 60))
        return self._token


def parse_feed(text: str) -> list[FigureRow]:
    rows = list(csv.DictReader(io.StringIO(text)))
    return [
        (r["section"], r["label"], r["typology"], r["week_start"], int(r["value"])) for r in rows
    ]


async def _pull_dashboard(
    board: Dashboard, mart: Mart, valkey: Valkey, slot: int, summary: Summary
) -> None:
    tokens = TokenSource(board.token_url, board.client_id, board.secret)
    http = httpx.AsyncClient(base_url=board.conduit_url, timeout=60.0)
    try:
        try:
            listed = await http.get(
                "/v1/investigations", headers={"Authorization": f"Bearer {await tokens.get()}"}
            )
        except SyncRefused as refused:
            summary.failed += 1
            summary.failures.append(f"{board.client_id}: {refused}")
            for case_id in [p["case_id"] for p in await mart.pulls(board.client_id)]:
                await mart.record_failure(board.client_id, case_id, str(refused), datetime.now(UTC))
            return
        if listed.status_code != 200:
            summary.failed += 1
            summary.failures.append(
                f"{board.client_id}: the case list was refused ({listed.status_code})"
            )
            return
        for case in listed.json():
            case_id, case_name = str(case["id"]), str(case.get("name") or "")
            claimed = await valkey.set(
                f"report-sync:{board.client_id}:{case_id}:{slot}", "1", nx=True, ex=86400
            )
            if not claimed:
                summary.skipped += 1
                continue
            try:
                feed = await http.get(
                    f"/v1/investigations/{case_id}/reports/feed",
                    params={"weeks": board.weeks, "format": "csv"},
                    headers={"Authorization": f"Bearer {await tokens.get()}"},
                )
                if feed.status_code != 200:
                    raise SyncRefused(f"the feed was refused ({feed.status_code})")
                summary.changed += await mart.replace(
                    board.client_id,
                    case_id,
                    case_name,
                    board.weeks,
                    parse_feed(feed.text),
                    datetime.now(UTC),
                )
                summary.pulled += 1
            except (SyncRefused, httpx.HTTPError, ValueError, KeyError) as e:
                summary.failed += 1
                summary.failures.append(f"{board.client_id} / {case_name}: {e}")
                await mart.record_failure(board.client_id, case_id, str(e), datetime.now(UTC))
    finally:
        await tokens.aclose()
        await http.aclose()


async def sync_once(
    dashboards: Sequence[Dashboard], mart: Mart, valkey: Valkey, *, slot: int
) -> Summary:
    """One pass over every configured dashboard; `slot` names the period being claimed."""
    summary = Summary()
    await mart.prune([d.client_id for d in dashboards])
    for board in dashboards:
        await _pull_dashboard(board, mart, valkey, slot, summary)
    return summary


__all__ = ["Dashboard", "Summary", "SyncRefused", "TokenSource", "parse_feed", "sync_once"]
