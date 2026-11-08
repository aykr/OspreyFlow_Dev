"""Derive's closed catalogue of operations (ADR-140 decision 11; `09_INGEST_STUDIO.md` §9; rule 8).

A Derive staging step makes one new column from a row's cells by naming an operation from this
catalogue and declaring its settings. There is no expression language: the operation is a name
looked up here, never code, and each one has a golden file
(`tests/knowledge_adapters/golden/derive/<operation>.json`). Like every Knowledge Adapter it rejects
rather than guesses, raising `NormalisationError` (adapter `derive.<operation>`), so the staging
step rejects that row with its cause, as the Map step rejects a row a transform refuses.

Every operation takes the row's cells for its declared columns, in their declared order, as text or
`None` for an empty cell, and gives text or `None`. An empty input gives `None` (nothing to derive
from) except where the operation says otherwise; a refusal is for a value or a setting that is
wrong, never for an empty cell.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, Inexact, InvalidOperation, Overflow, localcontext
from typing import Any

from .datetime_adapter import datetime_adapter
from .errors import NormalisationError

Cells = Sequence[str | None]
Operation = Callable[[Cells, Mapping[str, Any]], str | None]


def _refuse(operation: str, values: Cells, reason: str) -> NormalisationError:
    return NormalisationError(f"derive.{operation}", " | ".join(v or "" for v in values), reason)


def _text(value: str | None) -> str | None:
    """A cell as text, trimmed; blank is empty."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _one(operation: str, values: Cells) -> str | None:
    if len(values) != 1:
        raise _refuse(operation, values, f"{operation} takes one column, not {len(values)}")
    return _text(values[0])


def _concat(values: Cells, params: Mapping[str, Any]) -> str | None:
    if len(values) < 2:
        raise _refuse("concat", values, "concat takes at least two columns")
    separator = str(params.get("separator", " "))
    parts = [t for t in (_text(v) for v in values) if t is not None]
    return separator.join(parts) if parts else None


def _split(values: Cells, params: Mapping[str, Any]) -> str | None:
    """One part, by position, of what the `split` adapter gives (trimmed parts, empty ones
    dropped, a repeated one kept once at its first place), so Derive's split and Map's never
    disagree about a cell."""
    from .split import split as split_adapter

    delimiter = str(params.get("delimiter", "|"))
    part = int(params.get("part", 0))
    if delimiter == "":
        raise _refuse("split", values, "the delimiter is empty, so no part can be told apart")
    if part < 0:
        raise _refuse("split", values, "part must be 0 or more (the first part is 0)")
    text = _one("split", values)
    if text is None:
        return None
    parts = split_adapter(text, delimiter=delimiter)
    return parts[part] if part < len(parts) else None


def _substring(values: Cells, params: Mapping[str, Any]) -> str | None:
    start = int(params.get("start", 0))
    length = params.get("length")
    if start < 0:
        raise _refuse("substring", values, "start must be 0 or more (the first character is 0)")
    if length is not None and int(length) < 1:
        raise _refuse("substring", values, "length must be 1 or more")
    text = _one("substring", values)
    if text is None or start >= len(text):
        return None
    end = None if length is None else start + int(length)
    return text[start:end]


def _date_parse(values: Cells, params: Mapping[str, Any]) -> str | None:
    text = _one("date_parse", values)
    if text is None:
        return None
    try:
        parsed = datetime_adapter(text, tz=params.get("tz"), date_order=params.get("date_order"))
    except NormalisationError as exc:
        raise _refuse("date_parse", values, exc.reason) from exc
    return parsed.utc.isoformat()


#: A result past 1E±100 is refused rather than written out in full as a cell of that many digits.
_LARGEST_EXPONENT = 100

_ARITHMETIC = {
    "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
    "multiply": lambda a, b: a * b,
    "divide": lambda a, b: a / b,
}


def _number(values: Cells, text: str) -> Decimal:
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise _refuse("arithmetic", values, "a cell is not a number") from exc
    if not number.is_finite():
        raise _refuse("arithmetic", values, "a cell is not a number")
    return number


def _arithmetic(values: Cells, params: Mapping[str, Any]) -> str | None:
    op = params.get("op")
    if op not in _ARITHMETIC:
        raise _refuse(
            "arithmetic", values, f"unknown operation {op!r}: add, subtract, multiply or divide"
        )
    constant = params.get("constant")
    if not ((len(values) == 1 and constant is not None) or (len(values) == 2 and constant is None)):
        raise _refuse(
            "arithmetic", values, "arithmetic takes one column with a constant, or two columns"
        )
    cells = [_text(v) for v in values]
    if any(c is None for c in cells):
        return None
    operands = [_number(values, c) for c in cells if c is not None]
    if constant is not None:
        operands.append(_number(values, str(constant)))
    if op == "divide" and operands[1] == 0:
        raise _refuse("arithmetic", values, "division by zero")
    # Add, subtract and multiply are exact or refused: a result the context would have to round is
    # never written as if it were the sum. A quotient is given to 28 significant figures, as
    # 09 §4 says, since most quotients have no exact decimal.
    with localcontext() as context:
        context.prec = 28 if op == "divide" else 200
        context.traps[Inexact] = op != "divide"
        try:
            result = _ARITHMETIC[op](operands[0], operands[1])
        except Overflow as exc:
            raise _refuse(
                "arithmetic", values, "the result is too large or too small to write"
            ) from exc
        except Inexact as exc:
            raise _refuse("arithmetic", values, "the result cannot be written exactly") from exc
        if result.is_finite() and result != 0 and abs(result.adjusted()) > _LARGEST_EXPONENT:
            raise _refuse("arithmetic", values, "the result is too large or too small to write")
        # `normalize` writes 40 as 4E+1; a number is written plainly. Inside the same context, so
        # it never rounds what the operation kept.
        return format(result.normalize(), "f")


def _case_when(values: Cells, params: Mapping[str, Any]) -> str | None:
    cases = list(params.get("cases") or [])
    if not cases:
        raise _refuse("case_when", values, "case_when needs at least one case")
    seen: set[str] = set()
    for case in cases:
        equals = str(case["equals"])
        if equals in seen:
            raise _refuse("case_when", values, f"case_when names {equals} twice")
        seen.add(equals)
    text = _one("case_when", values)
    for case in cases:
        if text is not None and text == str(case["equals"]):
            return str(case["then"])
    otherwise = params.get("otherwise")
    return None if otherwise is None else str(otherwise)


@functools.cache
def text_adapters() -> frozenset[str]:
    """The Knowledge Adapters that read one column into one value of text: what a Derive's
    `normalise`, and a Lookup's or a Join's key, may name. An adapter whose result is structured
    (`datetime`, `person_name`, `address`, `card`) is bound one part at a time in Map, never
    written whole as a cell; one that gives a list (`split`) or reads several columns is not one
    value of one column."""
    import typing

    from . import ARITY, REGISTRY

    return frozenset(
        name
        for name, adapter in REGISTRY.items()
        if name not in ARITY and typing.get_type_hints(adapter).get("return") is str
    )


def _normalise(values: Cells, params: Mapping[str, Any]) -> str | None:
    from . import REGISTRY

    name = params.get("adapter")
    if name not in text_adapters():
        raise _refuse(
            "normalise",
            values,
            f"{name!r} is not a Knowledge Adapter that reads one column into one value of text",
        )
    text = _one("normalise", values)
    if text is None:
        return None
    try:
        result = REGISTRY[name](text)
    except NormalisationError as exc:
        raise _refuse("normalise", values, f"{exc.adapter}: {exc.reason}") from exc
    return str(result)


#: The catalogue (brief §6: concat, split, substring, date parse / zone, arithmetic, case/when,
#: normalise-as-adapter). Closed: a Derive step naming anything else is refused.
DERIVE_OPERATIONS: dict[str, Operation] = {
    "concat": _concat,
    "split": _split,
    "substring": _substring,
    "date_parse": _date_parse,
    "arithmetic": _arithmetic,
    "case_when": _case_when,
    "normalise": _normalise,
}


def derive(operation: str, values: Cells, params: Mapping[str, Any]) -> str | None:
    """Run one catalogued operation over a row's cells, or refuse in words."""
    op = DERIVE_OPERATIONS.get(operation)
    if op is None:
        raise NormalisationError(
            f"derive.{operation}",
            " | ".join(v or "" for v in values),
            f"{operation!r} is not in Derive's catalogue",
        )
    try:
        return op(values, params)
    except NormalisationError:
        raise
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        # A setting or a cell the operation cannot read refuses the row; it never stops the run.
        # The schema refuses wrong settings before a run (`schemas.staging`); this is the floor.
        raise NormalisationError(
            f"derive.{operation}",
            " | ".join(v or "" for v in values),
            f"{operation} cannot read its settings or this row's cells ({type(exc).__name__})",
        ) from exc
