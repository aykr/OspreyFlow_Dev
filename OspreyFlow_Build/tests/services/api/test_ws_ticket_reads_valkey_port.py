"""CO3b: `test_ws_ticket.py`'s `valkey` fixture opens the Valkey at `VALKEY_PORT`, not at a fixed
6379, which is one stack's port and is refused by the port guard from any other.

Pure: nothing here connects. Building a `Valkey` client only records its settings in the client's
connection pool (a socket is opened by the first command, and no command is sent), so the port is
read from `client.connection_pool.connection_kwargs`. The fixture under test is the real one,
imported from `test_ws_ticket.py` and run by pytest itself.
"""

from __future__ import annotations

import pytest
from valkey.asyncio import Valkey

from tests.services.api import test_ws_ticket

# The fixture under test. pytest finds a fixture by the name it is bound to in this module.
valkey = test_ws_ticket.valkey

# No stack's Valkey is here (stacks a to g hold 6379 to 6385), and nothing connects to it.
_UNUSED_PORT = 59983


@pytest.fixture
def pinned_port(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("VALKEY_PORT", str(_UNUSED_PORT))
    return _UNUSED_PORT


@pytest.fixture
def unset_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VALKEY_PORT", raising=False)


def _port(client: Valkey) -> int:
    return client.connection_pool.connection_kwargs["port"]


# pytest sets fixtures up in the order the signature names them, so the environment is arranged
# before the fixture under test reads it.


async def test_the_fixtures_client_takes_valkey_port(pinned_port: int, valkey: Valkey) -> None:
    assert _port(valkey) == pinned_port


async def test_the_fixtures_client_takes_6379_when_valkey_port_is_unset(
    unset_port: None, valkey: Valkey
) -> None:
    assert _port(valkey) == 6379
