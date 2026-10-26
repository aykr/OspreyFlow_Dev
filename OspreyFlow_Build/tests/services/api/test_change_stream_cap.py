"""The change stream is capped by entries (`CHANGE_STREAM_MAXLEN`): `publish` passes the cap to
`XADD` as an approximate `MAXLEN ~`. Valkey is run `noeviction`, an entry now carries every node a
run touched, and nothing reads an entry after the fact (evaluation runs with the entry in hand), so
an uncapped stream would grow until writes failed. Pure: the client is a recording fake; the live
proof that the length stays bounded is `test_change_stream.py`'s.

The cap is below `read_since`'s window by more than the approximate trim's slack (it removes whole
macro nodes, 100 entries by default), so a read from the start of the stream always reaches its
newest entry: the tests that look for their own entry in `read_since()` keep working."""

from __future__ import annotations

from typing import Any

from services.api.change_stream import CHANGE_STREAM_MAXLEN, READ_SINCE_COUNT, ChangeStreamWriter


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def xadd(self, *args: Any, **kwargs: Any) -> bytes:
        self.calls.append((args, kwargs))
        return b"1-0"


async def test_publish_passes_the_cap_to_xadd_as_an_approximate_maxlen() -> None:
    client = _Client()
    await ChangeStreamWriter(client).publish("manual_assertion", edge_ids=["e1"])  # type: ignore[arg-type]
    ((args, kwargs),) = client.calls
    assert args[0] == "changes:corpus"
    assert kwargs.get("maxlen") == CHANGE_STREAM_MAXLEN
    assert kwargs.get("approximate") is True


def test_the_cap_leaves_a_whole_stream_inside_the_read_window() -> None:
    # An approximate trim keeps up to one macro node (100 entries by default) over the cap.
    assert CHANGE_STREAM_MAXLEN + 100 <= READ_SINCE_COUNT
