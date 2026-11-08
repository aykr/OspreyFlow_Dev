"""A stand-in for the analytics store, for tests whose alerts cite no transaction (`06_DECISIONS.md`
ADR-146 decision 10): the queue and the inbox read an alert's transactions only when it cites some,
so nothing here is ever asked. If it is, the test's alerts cite a transaction after all, and it must
read them from a real analytics store: this refuses rather than answer for one (rule 15).
"""

from __future__ import annotations

from typing import Any


class NoTransactions:
    async def list_events(self, *_: Any, **__: Any) -> Any:
        raise AssertionError(
            "this test's alerts cite a transaction: read it from a real analytics store"
        )


NO_TRANSACTIONS: Any = NoTransactions()
