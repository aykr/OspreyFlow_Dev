"""Screening lists and name screening (`06_DECISIONS.md` ADR-109 phase F, the KYC addendum's
Component 6).

**A screening list is not a hotlist, and not graph content.** A hotlist (ADR-038) is one owner's one
exact identifier; a screening list is a licensed register — sanctions, politically exposed persons,
adverse media — of names matched fuzzily, deployment-wide. It is held here, outside the graph, so
that only an entry a customer actually matches ever enters a case (data minimisation: a real list,
admitted locally under the owner's exceptions file, is never copied wholesale into the graph).

**Matching reuses the resolution engine's own comparison.** Names are compared with DuckDB's
`jaro_winkler_similarity` — the function `ontology/resolution_functions.py` maps
`jaro_winkler(...)` to for Splink — over each name's tokens in sorted order, so "PETROV, Elena" and
"Elena Petrov" agree. A date of birth on both sides that disagrees rules the pair out. A hit is a
suggestion, scored, for a person to judge (rule 5): it is written `inferred`, never asserted.

**Rule 9.** Everything committed is synthetic
(`packages/demo_fixtures/screening_list_synthetic.yaml`).
`scripts/load_screening_list.py` refuses a list not marked synthetic unless the owner's local
`real_data_exceptions.yaml` names it — OpenSanctions (CC-BY-NC 4.0, spec 00 §7) included.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

import asyncpg
import duckdb

Listing = Literal["sanction", "pep", "adverse_media"]

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS screening_entries (
    id TEXT PRIMARY KEY,
    list_name TEXT NOT NULL,
    listing TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    date_of_birth DATE,
    country TEXT,
    synthetic BOOLEAN NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS screening_entries_type_idx ON screening_entries (entity_type);
"""


@dataclass(frozen=True)
class ScreeningEntry:
    id: str
    list_name: str
    listing: Listing
    entity_type: Literal["Person", "Organisation"]
    name: str
    date_of_birth: date | None = None
    country: str | None = None
    synthetic: bool = True


@dataclass(frozen=True)
class ScreeningHit:
    entry: ScreeningEntry
    score: float


def normalised(name: str) -> str:
    """Case, accents and punctuation folded away, tokens sorted: the form two spellings of one name
    share."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", folded.casefold())
    return " ".join(sorted(tokens))


def screen(
    name: str,
    date_of_birth: date | None,
    entries: Sequence[ScreeningEntry],
    *,
    min_score: float,
) -> list[ScreeningHit]:
    """Every entry the name matches at `min_score` or above, best first; an entry whose date of
    birth disagrees with a known one is not a match, however close the name."""
    probe = normalised(name)
    if not probe or not entries:
        return []
    candidates = [
        e
        for e in entries
        if not (date_of_birth and e.date_of_birth and e.date_of_birth != date_of_birth)
    ]
    if not candidates:
        return []
    con = duckdb.connect()
    try:
        scores = con.execute(
            "SELECT jaro_winkler_similarity(?, unnest(?::VARCHAR[]))",
            [probe, [normalised(e.name) for e in candidates]],
        ).fetchall()
    finally:
        con.close()
    hits = [
        ScreeningHit(entry=e, score=round(float(row[0]), 4))
        for e, row in zip(candidates, scores, strict=True)
        if float(row[0]) >= min_score
    ]
    return sorted(hits, key=lambda h: (-h.score, h.entry.id))


class ScreeningListStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> ScreeningListStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def replace_list(self, list_name: str, entries: Sequence[ScreeningEntry]) -> int:
        """The named list, replaced whole in one transaction — a reload never leaves half of an
        old list beside half of a new one."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM screening_entries WHERE list_name = $1", list_name)
            await conn.executemany(
                "INSERT INTO screening_entries (id, list_name, listing, entity_type, name, "
                "date_of_birth, country, synthetic, loaded_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                [
                    (e.id, list_name, e.listing, e.entity_type, e.name, e.date_of_birth,
                     e.country, e.synthetic, now)
                    for e in entries
                ],
            )  # fmt: skip
        return len(entries)

    async def entries(self, entity_type: str) -> list[ScreeningEntry]:
        """Reference data, read by the screening rules' evaluation only (never a route)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, list_name, listing, entity_type, name, date_of_birth, country, "
                "synthetic FROM screening_entries WHERE entity_type = $1 ORDER BY id",
                entity_type,
            )
        return [
            ScreeningEntry(
                id=r["id"], list_name=r["list_name"], listing=r["listing"],
                entity_type=r["entity_type"], name=r["name"], date_of_birth=r["date_of_birth"],
                country=r["country"], synthetic=r["synthetic"],
            )  # fmt: skip
            for r in rows
        ]


__all__ = [
    "ScreeningEntry",
    "ScreeningHit",
    "ScreeningListStore",
    "normalised",
    "screen",
]
