"""Delta fan-out between a mutating REST call and any open WebSocket on
the same investigation — `spec/03_CONDUIT_MIDDLEWARE.md` §3.2's "bidirectional
delta channel" needs a way for a mutation landed by *one* Conduit instance
to reach a client whose WebSocket happens to be held open by *another*
instance (`03_CONDUIT_MIDDLEWARE.md` §1: statelessness means any instance
serves any request). Valkey Pub/Sub, not an in-process fan-out, is what
makes that true regardless of which instance the mutation and the open
socket happen to land on.

This is deliberately not part of `WorkingSetStorage`/`WorkingSetService`:
those two own the *durable* delta (the capped stream a reconnect replays
from), which is correct and complete on its own — nothing here is load
bearing for correctness, only for how quickly an *already-connected*
client sees a delta it didn't cause itself. A missed publish is invisible
to the byte-identical-set guarantee, since a client whose socket drops
resyncs from the durable stream regardless (`working_set/service.py`'s
`sync`), never from this channel.
"""

from __future__ import annotations

from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply as _reply

from .working_set.models import DeltaRemoveSent, DeltaReplaceEdgeSent, WorkingSetDelta


def notify_channel(investigation_id: str) -> str:
    return f"ws:{investigation_id}:notify"


async def publish_delta(client: Valkey, investigation_id: str, delta: WorkingSetDelta) -> None:
    """Publishes the stored form of a delta, record included (ADR-124 decision 4): every socket's
    own projection decides what its reader is sent of it. The stored and sent forms are separate
    types, so the checker refuses a sent one; the check below is for a caller it does not see,
    since nothing can be projected from a sent form."""
    if isinstance(delta, DeltaRemoveSent | DeltaReplaceEdgeSent):
        raise TypeError(f"a sent {type(delta).__name__} has no record to project readers from")
    await _reply(client.publish(notify_channel(investigation_id), delta.model_dump_json()))
