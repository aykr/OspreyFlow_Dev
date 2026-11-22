"""SE8c, round 2: the shipped Conduit installs the watch that records first-seen sessions and the
page service's reports (rule 12; `RULINGS.md` SE8).

The acceptance test (`test_sign_in_events.py`) builds its own `SignInWatch` and sets it on the app,
as it must, because the real start-up needs Valkey and Postgres. That leaves one line unproved:
in `services/api/app.py`'s `lifespan`, `app.state.sign_in_watch = SignInWatch(valkey, audit)`. If it
is gone, or built over the wrong store, or set only on some path, the shipped Conduit writes no
`sign_in_seen` row and answers every `POST /v1/session-events` with 503, while every other test
stays green (both read sites fall back without a word for an app with no watch, as a test app has).

The start-up cannot run in a pure test, so this reads `lifespan` as a syntax tree, and says what it
requires of it:

1. there is exactly one assignment to `app.state.sign_in_watch` in `app.py`, in `lifespan`;
2. it is a statement of `lifespan`'s own body (not under an `if`, `try` or loop), before the
   `try`/`yield` that starts serving: so every start installs it;
3. it builds `SignInWatch(valkey, audit)`, where those are the very names `lifespan` also puts on
   `app.state.valkey` and `app.state.audit` (the working-set Valkey and the audit writer every
   route writes through), and `valkey` and `audit` are read from the one resources object.

**Rule 15: planted at the shape the file really has.** The checker is a function of the source text;
each case below edits the real `app.py` text (removes the line, swaps the stores, hands it a third
store, nests it under a condition, moves it after the yield) and asserts the checker reports it.

**Folders walked:** `OspreyFlow_Core/services/api/app.py`, read, not run.
**Owed to a live stack:** that a started Conduit really records over a real Valkey and Postgres
(the live step is off).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
APP_PY = REPO / "OspreyFlow_Core" / "services" / "api" / "app.py"
LINE = "    app.state.sign_in_watch = SignInWatch(valkey, audit)\n"


def _state_target(node: ast.stmt, name: str) -> bool:
    """`app.state.<name> = ...`, as a statement."""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return False
    t = node.targets[0]
    return (
        isinstance(t, ast.Attribute)
        and t.attr == name
        and isinstance(t.value, ast.Attribute)
        and t.value.attr == "state"
        and isinstance(t.value.value, ast.Name)
        and t.value.value.id == "app"
    )


def watch_wiring_faults(source: str) -> list[str]:
    """What is wrong with the way `lifespan` installs the watch; empty when it is installed."""
    tree = ast.parse(source)
    faults: list[str] = []
    lifespans = [
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
    ]
    if len(lifespans) != 1:
        return ["there is not exactly one `lifespan`"]
    life = lifespans[0]

    everywhere = [
        n for n in ast.walk(tree) if isinstance(n, ast.Assign) and _state_target(n, "sign_in_watch")
    ]
    if len(everywhere) != 1:
        faults.append(f"`app.state.sign_in_watch` is assigned {len(everywhere)} times, not once")
    direct = [s for s in life.body if _state_target(s, "sign_in_watch")]
    if not direct:
        faults.append("`lifespan` has no top-level statement installing `app.state.sign_in_watch`")
        return faults
    stmt = direct[0]
    assert isinstance(stmt, ast.Assign)
    if everywhere and everywhere[0] is not stmt:
        faults.append("the installation is not a statement of `lifespan`'s own body")

    serving = next(
        (i for i, s in enumerate(life.body) if any(isinstance(n, ast.Yield) for n in ast.walk(s))),
        None,
    )
    if serving is None or life.body.index(stmt) > serving:
        faults.append("the watch is installed after the Conduit starts serving, not before")

    value = stmt.value
    if not (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "SignInWatch"
        and not value.keywords
        and len(value.args) == 2
    ):
        faults.append("it is not `SignInWatch(<valkey>, <audit>)`")
        return faults
    got = [ast.unparse(a) for a in value.args]

    def stores(name: str) -> str | None:
        for s in life.body:
            if _state_target(s, name) and isinstance(s, ast.Assign):
                return ast.unparse(s.value)
        return None

    if got != [stores("valkey"), stores("audit")]:
        faults.append(
            f"it is built over {got}, not over what `app.state.valkey` and `app.state.audit` hold "
            f"({[stores('valkey'), stores('audit')]})"
        )

    def resource_attr(var: str) -> str | None:
        for s in life.body:
            if (
                isinstance(s, ast.Assign)
                and len(s.targets) == 1
                and isinstance(s.targets[0], ast.Name)
                and s.targets[0].id == var
            ):
                return ast.unparse(s.value)
        return None

    for var in ("valkey", "audit"):
        if resource_attr(var) != f"resources.{var}":
            faults.append(f"`{var}` is not read from `resources.{var}`")
    return faults


def real() -> str:
    return APP_PY.read_text()


def test_the_shipped_lifespan_installs_the_watch_over_the_stores_every_route_uses() -> None:
    assert watch_wiring_faults(real()) == []


def test_the_text_the_plants_edit_is_the_real_text() -> None:
    """A plant that edits nothing proves nothing: the line the plants change is in the file."""
    assert real().count(LINE) == 1


@pytest.mark.parametrize(
    ("name", "edit", "says"),
    [
        ("the line removed", lambda s: s.replace(LINE, ""), "no top-level statement"),
        (
            "the stores swapped",
            lambda s: s.replace(LINE, "    app.state.sign_in_watch = SignInWatch(audit, valkey)\n"),
            "is built over",
        ),
        (
            "a third store handed in",
            lambda s: s.replace(LINE, "    app.state.sign_in_watch = SignInWatch(None, audit)\n"),
            "is built over",
        ),
        (
            "the audit writer left out",
            lambda s: s.replace(LINE, "    app.state.sign_in_watch = SignInWatch(valkey)\n"),
            "not `SignInWatch(<valkey>, <audit>)`",
        ),
        (
            "built over a name that is not the audit writer on the state",
            lambda s: s.replace(
                LINE, "    app.state.sign_in_watch = SignInWatch(valkey, model_admin_audit)\n"
            ),
            "is built over",
        ),
        (
            "installed only under a condition",
            lambda s: s.replace(
                LINE,
                "    if config is not None:\n"
                "        app.state.sign_in_watch = SignInWatch(valkey, audit)\n",
            ),
            "no top-level statement",
        ),
        (
            "installed twice",
            lambda s: s.replace(LINE, LINE + LINE),
            "assigned 2 times",
        ),
        (
            "installed in a different name",
            lambda s: s.replace(
                LINE, "    app.state.sign_in_watcher = SignInWatch(valkey, audit)\n"
            ),
            "no top-level statement",
        ),
    ],
)
def test_the_wiring_check_fails_for_each_planted_fault(name: str, edit, says: str) -> None:  # type: ignore[no-untyped-def]
    planted = edit(real())
    assert planted != real(), name
    faults = watch_wiring_faults(planted)
    assert faults, f"{name}: the check found nothing"
    assert any(says in f for f in faults), (name, faults)


def test_the_wiring_check_fails_for_a_watch_installed_after_the_conduit_starts_serving() -> None:
    """Moved to the end of `lifespan`'s own body, after its `try`/`yield`."""
    source = real().replace(LINE, "")
    marker = "\n\n# The OpenAPI document is published at `GET /v1/openapi.json`"
    assert source.count(marker) == 1
    planted = source.replace(marker, "\n" + LINE.rstrip("\n") + marker)
    faults = watch_wiring_faults(planted)
    assert any("after the Conduit starts serving" in f for f in faults), faults


def test_the_wiring_check_fails_when_valkey_is_not_the_resources_one() -> None:
    planted = real().replace(
        "    valkey = resources.valkey\n", "    valkey = make_other_valkey()\n"
    )
    assert planted != real()
    assert any(
        "`valkey` is not read from `resources.valkey`" in f for f in watch_wiring_faults(planted)
    )
