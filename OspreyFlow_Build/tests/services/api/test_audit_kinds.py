"""Every audit action the Conduit writes is classified in Admin › Audit (`06_DECISIONS.md` ADR-145
decision 10, Amendment 6; rule 12).

`test_audit_section_routes.py::test_every_kinds_action_is_one_the_conduit_records` checks the other
direction (each named action is written somewhere): it cannot see an action written and named
nowhere, which Audit would file under *Reads and refusals* by default. That default withholds its
words, so it never shows too much, but a kind's filter would silently miss it. This finds every
action written in `services/` and `scripts/` by reading the source's syntax tree:

- `….record(action=<string>)`, or a conditional of two strings, or a name assigned one in the same
  function or at a module's top level;
- a helper whose `action` parameter reaches `….record(action=…)`, at each of its calls;
- an f-string, as the family of its fixed prefix (`compute_<metric>`).

Anything else is reported as unresolved and fails too, so the scan cannot quietly lose a writer.
"""

from __future__ import annotations

import ast
import pathlib

CORE = pathlib.Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
SERVICES = CORE / "services"
#: Every tree that writes to the audit stream: the Conduit's and the Studio's services, and the
#: operator's scripts (a seed, a revert, a sweep), which write through the same `AuditWriter`.
WRITERS = (SERVICES, CORE / "scripts")

_Found = tuple[set[str], set[str]]


def _module_constants(trees: dict[pathlib.Path, ast.Module]) -> dict[str, str]:
    out: dict[str, str] = {}
    for tree in trees.values():
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):  # fmt: skip
                out[node.targets[0].id] = node.value.value
    return out


def _consts(node: ast.AST | None, local: dict[str, _Found], glob: dict[str, str]) -> _Found | None:
    """The actions an expression can be: (exact names, f-string prefixes), or None if unknown."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}, set()
    if isinstance(node, ast.IfExp):
        a, b = _consts(node.body, local, glob), _consts(node.orelse, local, glob)
        return None if a is None or b is None else (a[0] | b[0], a[1] | b[1])
    if isinstance(node, ast.Name):
        if node.id in local:
            return local[node.id]
        if node.id in glob:
            return {glob[node.id]}, set()
    if (isinstance(node, ast.JoinedStr) and node.values
            and isinstance(node.values[0], ast.Constant) and isinstance(node.values[0].value, str)):  # fmt: skip
        return set(), {node.values[0].value}
    return None


def _locals(fn: ast.AST, glob: dict[str, str]) -> dict[str, _Found]:
    out: dict[str, _Found] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
            node.targets[0], ast.Name
        ):
            found = _consts(node.value, {}, glob)
            if found is not None:
                out[node.targets[0].id] = found
    return out


_Fn = ast.FunctionDef | ast.AsyncFunctionDef


def written_actions(root: pathlib.Path = SERVICES) -> tuple[set[str], set[str], list[str]]:
    """(actions, f-string prefixes, unresolved call sites) written under `root`."""
    trees = {p: ast.parse(p.read_text()) for p in sorted(root.rglob("*.py"))}
    glob = _module_constants(trees)
    actions: set[str] = set()
    prefixes: set[str] = set()
    unresolved: list[str] = []
    helpers: dict[str, set[tuple[int, str]]] = {}
    functions = [(p, fn) for p, t in trees.items() for fn in ast.walk(t) if isinstance(fn, _Fn)]

    def take(found: _Found | None, where: str) -> None:
        if found is None:
            unresolved.append(where)
        else:
            actions.update(found[0])
            prefixes.update(found[1])

    for path, fn in functions:
        params = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
        local = _locals(fn, glob)
        for call in ast.walk(fn):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "record"):  # fmt: skip
                continue
            for kw in call.keywords:
                if kw.arg != "action":
                    continue
                value = kw.value
                if isinstance(value, ast.Name) and value.id in params and value.id not in local:
                    helpers.setdefault(fn.name, set()).add((params.index(value.id), value.id))
                    continue
                take(_consts(value, local, glob), f"{path.name}:{call.lineno} {ast.unparse(value)}")
    for path, fn in functions:
        local = _locals(fn, glob)
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            f = call.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            for index, param in helpers.get(name, ()):
                arg = next((kw.value for kw in call.keywords if kw.arg == param), None)
                if arg is None:
                    at = index - (1 if isinstance(f, ast.Attribute) else 0)  # a method's self
                    arg = call.args[at] if 0 <= at < len(call.args) else None
                take(_consts(arg, local, glob), f"{path.name}:{call.lineno} {name}(…)")
    return actions, prefixes, sorted(set(unresolved))


def unclassified(*roots: pathlib.Path) -> list[str]:
    from services.api.audit_section import (
        _CLASSIFIED,
        READS_AND_OTHER,
        READS_AND_OTHER_PREFIXES,
    )
    from services.api.rule_evaluation import RULE_AUDIT_ACTIONS

    actions: set[str] = set()
    prefixes: set[str] = set()
    unresolved: list[str] = []
    for root in roots or WRITERS:
        found, fixed, lost = written_actions(root)
        actions |= found
        prefixes |= fixed
        unresolved += lost
    named = set(_CLASSIFIED) | set(READS_AND_OTHER) | set(RULE_AUDIT_ACTIONS)
    return sorted(
        [f"unresolved {u}" for u in unresolved]
        + [a for a in actions - named if not a.startswith(READS_AND_OTHER_PREFIXES)]
        + [f"prefix {p}" for p in prefixes - set(READS_AND_OTHER_PREFIXES)]
    )


def test_every_action_the_conduit_writes_is_classified() -> None:
    assert unclassified() == []


def test_the_scan_finds_the_conduits_writers() -> None:
    """A scan that found nothing would pass the test above: it must find the shapes it claims."""
    actions, prefixes, _ = written_actions()
    assert len(actions) > 200
    # A keyword string, a conditional, a local name, a module constant, a helper's argument.
    assert {"set_person_roles", "rule_change_proposed", "rule_retired", "load_reverted",
            "alert_close_proposed", "alert_disposed"} <= actions  # fmt: skip
    assert {"compute_", "dry_run_layer_"} <= prefixes


def test_an_action_written_and_named_nowhere_is_found(tmp_path: pathlib.Path) -> None:
    """Planted the way a route writes one (`await audit.record(principal=…, action="…")`), in a
    copy of the real services, beside a helper's call and an f-string family of its own."""
    import shutil

    copy = tmp_path / "services"
    shutil.copytree(SERVICES, copy, ignore=shutil.ignore_patterns("__pycache__"))
    with (copy / "api" / "app.py").open("a") as source:
        source.write(
            "\n\nasync def _planted(audit, principal):\n"
            "    await audit.record(principal=principal, action=\"planted_unclassified\",\n"
            "                       resolved_query={}, result_cardinality=0)\n"
            "    await _triage_audit(audit, principal, 'c1', 'planted_by_helper', None)\n"
            "    await audit.record(principal=principal, action=f\"planted_{principal}\",\n"
            "                       resolved_query={}, result_cardinality=0)\n"
        )
    found = set(unclassified(copy, CORE / "scripts")) - set(unclassified())
    assert sorted(found) == ["planted_by_helper", "planted_unclassified", "prefix planted_"]


def test_a_writer_the_scan_cannot_read_is_reported(tmp_path: pathlib.Path) -> None:
    """The docstring's promise: an action the scan cannot resolve (here an attribute, the shape a
    store writing its own `self.kind` would take) fails as unresolved, never passes unseen."""
    (tmp_path / "planted.py").write_text(
        "class Store:\n"
        "    async def write(self, audit, principal):\n"
        "        await audit.record(principal=principal, action=self.kind,\n"
        "                           resolved_query={}, result_cardinality=0)\n"
    )
    assert unclassified(tmp_path) == ["unresolved planted.py:3 self.kind"]
