"""One workaround, shared, instead of repeated in every module that talks
to Valkey.

`valkey.asyncio`'s stubs type every command as `Awaitable[T] | T` — shared
with the sync client's stubs — rather than `Awaitable[T]` alone, so a
plain `await` on a call through the async client does not type-check even
though it always actually returns a coroutine. `reply()` is the one cast
this whole codebase needs for that, called from `services/api/working_set/
store.py`, `services/api/jobs.py` and `services/api/cache.py` alike.
"""

from __future__ import annotations

from typing import Any


async def reply(value: Any) -> Any:
    return await value
