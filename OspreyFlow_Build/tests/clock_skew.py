"""A switch that moves the wall clock past a token's life once collection is over (slice CO2b).

`OSPREY_TEST_CLOCK_SKEW_SECONDS=N` makes every test see a clock N seconds later than the clock at
collection. It stands for a slow suite: GitHub's takes 40 to 49 minutes, the Mac's a few, and a token
minted while a test module was imported (a `parametrize` list calling `default_claims`) is N seconds old by
the time its test runs. Unset or 0, nothing changes.

Two clocks are moved, because token expiry is read from the second one: `time.time`, which the tests'
`default_claims` and the product read, and the `datetime` that PyJWT's `decode` reads (`jwt.api_jwt` takes
`datetime.now(tz=timezone.utc)`, not `time.time()`, so moving `time.time` alone would leave a stale
token valid and the switch would prove nothing). A token minted *inside* a test is stamped by the moved
clock and verified by the moved clock, so it stays valid whatever N is: that is the property under test.

It is a plugin (`tests.conftest` lists it in `pytest_plugins`), so a test can also load it with
`-p tests.clock_skew` into a run that has no conftest of ours, which `test_token_clock_independence.py`
does to show the switch itself works.
"""

from __future__ import annotations

import datetime as _datetime
import os
import time as _time

import pytest

ENV = "OSPREY_TEST_CLOCK_SKEW_SECONDS"

_real_time = _time.time
_applied: dict[str, object] = {}


def skew_seconds() -> float:
    raw = os.environ.get(ENV, "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError as err:
        raise pytest.UsageError(f"{ENV} must be a number of seconds, not {raw!r}") from err


class _ShiftedDatetimeMeta(type):
    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, _datetime.datetime)

    def __getattr__(cls, name: str) -> object:
        return getattr(_datetime.datetime, name)


def _shifted_datetime(seconds: float) -> type:
    """Stands in for `datetime.datetime` inside PyJWT: `now()` is later by `seconds`, everything else
    (isinstance checks, `fromtimestamp`, arithmetic) is the real class's."""

    class ShiftedDatetime(metaclass=_ShiftedDatetimeMeta):
        @staticmethod
        def now(tz: _datetime.tzinfo | None = None) -> _datetime.datetime:
            return _datetime.datetime.now(tz) + _datetime.timedelta(seconds=seconds)

    return ShiftedDatetime


def apply(seconds: float) -> None:
    """Move the clock `seconds` ahead from now. Idempotent per run: a second call replaces the first."""
    restore()
    if not seconds:
        return
    import jwt.api_jwt as api_jwt

    _applied["jwt_datetime"] = api_jwt.datetime
    _time.time = lambda: _real_time() + seconds  # type: ignore[assignment]
    api_jwt.datetime = _shifted_datetime(seconds)  # type: ignore[attr-defined]


def restore() -> None:
    if "jwt_datetime" in _applied:
        import jwt.api_jwt as api_jwt

        api_jwt.datetime = _applied.pop("jwt_datetime")  # type: ignore[attr-defined]
    _time.time = _real_time


def pytest_collection_finish(session: pytest.Session) -> None:
    """Collection is over: every module has been imported and every `parametrize` list evaluated. From
    here the clock is ahead, before the first test and so before each one."""
    apply(skew_seconds())


def pytest_report_header() -> str | None:
    seconds = skew_seconds()
    return f"clock skew: tests run {seconds:g} s after collection ({ENV})" if seconds else None


def pytest_unconfigure() -> None:
    restore()
