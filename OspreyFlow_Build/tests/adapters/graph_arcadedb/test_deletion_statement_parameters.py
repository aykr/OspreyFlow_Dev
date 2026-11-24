"""SE9c: the three statements that record a deletion name no parameter the real ArcadeDB refuses.

SE9 (ADR-144 Amendment 7, merge `2e13b10`) made the deleting write, the revert by load and the
dataset withdrawal record when and by whom, as `:at` and `:by`. Every test of them passed, and
GitHub's conformance job had 80 live tests red on one error:

    ArcadeDB error 400 ... CommandSQLParsingException ... SQL syntax error at line 1, column 68:
    mismatched input ',' expecting {<EOF>, ';'}
    UPDATE `mx_COMMUNICATED_WITH` SET reverted = true, reverted_at = :at, reverted_by = :by, ...

The fakes accepted whatever the adapter sent, so none of them could show it (rule 15, the 24
September worked example: a fixture models the dependency's refusals, not only its grants). Here the
refusals are named: `REFUSED_PARAMETER_NAMES` is what the live database turned away, and this test
fails when any statement the three code paths send names one of them, in its SQL text or as a key of
its parameters. No database is needed; the live twin is `test_deletion_statements_live.py`.

The three code paths, as SE9 wrote them: `revert_elements` (the deleting write, which also sets
`withdrawn_by_load = null`), `withdraw_elements` (the revert by load, `:load`) and `withdraw_layer`
(the dataset withdrawal, `:w`)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from adapters.graph_arcadedb import adapter as adapter_module
from ontology.handling import load_uk_le_scheme

#: The named parameters ArcadeDB's SQL parser refuses, with where that was shown. Found by SE9b's
#: builder on 23 November 2026 and shown again by SE9c's on 24 November 2026, each on a throwaway
#: ArcadeDB 26.10.1 under the stack lease: `UPDATE ... SET reverted_at = :at, reverted_by = :by,
#: ...` is refused (`mismatched input ',' expecting {<EOF>, ';'}`), the same statement with the
#: second parameter named `:whom` or `:by_whom` is accepted, and `SELECT :by` on its own is refused
#: (`no viable alternative at input 'by'`) while `SELECT :at` and `SELECT :whom` are accepted. The
#: likely reason is that `BY` is a keyword of ArcadeDB's SQL (`GROUP BY`, `ORDER BY`); the refusal
#: is what was measured, the reason is not. `at` is not refused: the first reading of the error,
#: which stops at the comma after `:at`, was wrong. Add a name only with a live proof beside it.
REFUSED_PARAMETER_NAMES = frozenset({"by"})

AT = datetime(2026, 11, 24, 9, 30, tzinfo=UTC)
WHO = "analyst-1"

# A parameter in SQL text: a colon not part of a word or of `schema:types`, then a name.
_NAMED = re.compile(r"(?<![\w:]):([A-Za-z_]\w*)")
_REVERTED_BY = re.compile(r"reverted_by = :(\w+)")


def refused_names_in(command: str, params: dict[str, Any] | None) -> set[str]:
    """The refused names a statement uses: named in its text, or keyed in its parameters. Names are
    compared in lower case, as the database reads a keyword."""
    named = {n.lower() for n in _NAMED.findall(command)}
    keyed = {str(k).lower() for k in (params or {})}
    return (named | keyed) & REFUSED_PARAMETER_NAMES


class RecordingStore:
    """A client that records each statement and its parameters, and answers what the three code
    paths read first: the types that carry a unique `id` index, which type holds each id, and the
    elements of a dataset layer. It answers any other statement it was not built for with a failure
    rather than an empty list, so a path that changed shape cannot pass by being ignored."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any] | None]] = []

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        self.sent.append((command, params))
        if command.startswith("SELECT name, type, indexes FROM schema:types"):
            index = [{"unique": True, "properties": ["id"]}]
            return [
                {"name": "Person", "type": "vertex", "indexes": index},
                {"name": "ASSOCIATE_OF", "type": "edge", "indexes": index},
            ]
        assert params is not None
        if (m := re.fullmatch(r"SELECT id FROM `(\w+)` WHERE id IN :ids", command)) is not None:
            held = {"Person": "n1", "ASSOCIATE_OF": "e1"}[m.group(1)]
            return [{"id": held}] if held in params["ids"] else []
        if re.fullmatch(
            r"SELECT id, datasets FROM `(\w+)` WHERE datasets CONTAINS :ds AND reverted = false",
            command,
        ):
            held = "n1" if "`Person`" in command else "e1"
            return [{"id": held, "datasets": [params["ds"]]}]
        if command == "INSERT INTO IndexPending CONTENT :rows":
            return []
        if command.startswith("UPDATE ") and "SET reverted = true" in command:
            return [{"count": len(params["ids"])}]
        raise AssertionError(f"unexpected SQL: {command}")

    def deleting(self) -> list[tuple[str, dict[str, Any]]]:
        return [(c, p) for c, p in self.sent if c.startswith("UPDATE ") and p is not None]


def _adapter(store: RecordingStore) -> adapter_module.GraphArcadeDBAdapter:
    return adapter_module.GraphArcadeDBAdapter(store, load_uk_le_scheme())  # type: ignore[arg-type]


async def _revert(graph: adapter_module.GraphArcadeDBAdapter) -> None:
    await graph.revert_elements(["n1"], ["e1"], "tx", by=WHO, at=AT)


async def _withdraw(graph: adapter_module.GraphArcadeDBAdapter) -> None:
    await graph.withdraw_elements(["n1"], ["e1"], "load-2", "tx", by=WHO, at=AT)


async def _layer(graph: adapter_module.GraphArcadeDBAdapter) -> None:
    await graph.withdraw_layer("layer-1", "layer-delete:case-a", "tx", by=WHO, at=AT)


PATHS = [
    pytest.param(_revert, id="revert_elements"),
    pytest.param(_withdraw, id="withdraw_elements"),
    pytest.param(_layer, id="withdraw_layer"),
]


@pytest.mark.parametrize("path", PATHS)
async def test_a_deleting_path_names_no_parameter_the_database_refuses(path: Any) -> None:
    store = RecordingStore()
    await path(_adapter(store))
    deleting = store.deleting()
    assert deleting, "the path sent a deleting statement (else this proves nothing)"
    for command, params in store.sent:
        refused = refused_names_in(command, params)
        assert not refused, (
            f"{sorted(refused)} is a name ArcadeDB's SQL refuses as a parameter "
            f"(see REFUSED_PARAMETER_NAMES); the statement: {command}"
        )


@pytest.mark.parametrize("path", PATHS)
async def test_the_name_given_to_who_is_in_the_text_and_the_parameters_together(path: Any) -> None:
    """The rename must reach both halves: the name the SQL text binds for `reverted_by`, and the
    key the parameters carry, with the one who deleted as its value; and `:at` binds the time."""
    store = RecordingStore()
    await path(_adapter(store))
    for command, params in store.deleting():
        named = _REVERTED_BY.search(command)
        assert named is not None, f"the statement records no `reverted_by`: {command}"
        assert params[named.group(1)] == WHO
        assert "reverted_at = :at" in command
        assert params["at"] == AT.isoformat()


def test_the_check_finds_the_statement_as_se9_sent_it() -> None:
    """The check shown red at the shape the adapter really sent on `2e13b10` (the revert's own
    statement text and parameter keys), not a bare word that would fail some other way."""
    sent = (
        "UPDATE `Person` SET reverted = true, reverted_at = :at, reverted_by = :by, "
        "withdrawn_by_load = null WHERE id IN :ids"
    )
    assert refused_names_in(sent, {"ids": ["n1"], "at": "2026-11-24", "by": WHO}) == {"by"}
    assert refused_names_in(sent, None) == {"by"}, "named in the text alone"
    assert refused_names_in(sent.replace(":by", ":whom"), {"by": WHO}) == {"by"}, (
        "keyed in the parameters alone"
    )
    fixed = sent.replace(":by", ":whom")
    assert refused_names_in(fixed, {"ids": ["n1"], "at": "2026-11-24", "whom": WHO}) == set()
    assert refused_names_in("SELECT name, type, indexes FROM schema:types", None) == set()
