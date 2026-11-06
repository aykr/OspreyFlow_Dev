"""The sources' refresh policies as the schedule executor runs them (`06_DECISIONS.md` ADR-110
Amendments 5 and 6).

`StoredSourceWatches` answers the executor's `SourceWatches`: every source with a folder watch,
each paired with every *deployed* pipeline of its dataset that reads its location (published, or
needing attention, which the executor records blocked; a draft is never run by a refresh). Each
pipeline then takes the source's waiting files itself, through the executor's watch path, so a
file runs every pipeline that reads the source once, under its own claim, lock and load.
"""

from __future__ import annotations

from typing import Any, Protocol

from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from schemas.sources import SourceTable

from .scheduler import SourceWatch

_DEPLOYED = (StudioRecipeStatus.PUBLISHED, StudioRecipeStatus.FLAGGED)


class _WatchedSources(Protocol):
    async def watched(self) -> list[SourceTable]: ...

    async def set_refresh_paused(
        self, source_id: str, *, paused: bool, reason: str | None
    ) -> None: ...


class _Readers(Protocol):
    async def using_source(self, dataset_id: str, location: str) -> list[Any]: ...


class StoredSourceWatches:
    def __init__(self, sources: _WatchedSources, recipes: _Readers) -> None:
        self._sources = sources
        self._recipes = recipes

    async def watching(self) -> list[tuple[StudioRecipeDraft, SourceWatch]]:
        pairs: list[tuple[StudioRecipeDraft, SourceWatch]] = []
        for source in await self._sources.watched():
            watch = SourceWatch(
                source_id=source.id,
                dataset_id=source.dataset_id,
                pattern=source.refresh.pattern or "",
                owner=source.refresh.owner,
                set_at=source.refresh.set_at,
                paused=source.refresh.paused,
                mode=source.refresh.mode,
                dropped_rows=source.refresh.dropped_rows,
                watermark_column=source.refresh.watermark_column,
            )
            for recipe in await self._recipes.using_source(source.dataset_id, source.location):
                if recipe.status in _DEPLOYED:
                    pairs.append((recipe, watch))
        return pairs

    async def set_paused(self, source_id: str, *, paused: bool, reason: str | None) -> None:
        await self._sources.set_refresh_paused(source_id, paused=paused, reason=reason)
