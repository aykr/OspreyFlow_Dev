"""A Reports Viewer reads in Superset and writes nothing there (the owner's ruling, 16 November 2026).

v0.6.0's package test found a Reports Viewer, signed in to Superset as its built-in Gamma, saving a
dashboard: Gamma holds `can_write` on Dashboard and on Chart and other writes besides, though the owner's
ruling of 13 November and `superset_config.py` called it read-only. And Flask-AppBuilder adds the
registration role to every account while registration is on, so a reader's role remapped alone would
still have come with Gamma's writes.

So Superset's OspreyFlow roles give a reader `OspreyReader` (`deploy/superset/osprey_roles.py`): Gamma
less every permission named for a write, but for the few that keep a person's own session's state
(a dashboard's filters, a link to share, the explore form, their own settings), each named with its
reason. A write a later Superset adds to Gamma is left out until someone names it. `superset_config.py`
maps the Reports Viewer to it and makes it the registration role.

What a mistake would do, and the case that catches it (rule 12):
- a write of Gamma's left in the reader's role, read from Gamma's own table in this image
  (`tests/fixtures/superset/gamma_permissions.txt`): `test_the_reader_holds_none_of_gamma_s_writes`;
- the reader's reading lost with the writes: `test_the_reader_keeps_every_read_gamma_has`;
- the Reports Viewer mapped to Gamma, or Gamma still the registration role every account gets:
  `test_the_config_maps_the_reports_viewer_and_registers_everyone_as_the_reader`;
- the role defined but not made at start: `test_superset_s_setup_makes_the_reader_from_gamma`.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from tools.layout import CORE

SUPERSET = CORE / "deploy" / "superset"
GAMMA_TABLE = Path(__file__).parent / "fixtures" / "superset" / "gamma_permissions.txt"

_spec = importlib.util.spec_from_file_location("osprey_roles", SUPERSET / "osprey_roles.py")
assert _spec and _spec.loader
osprey_roles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(osprey_roles)


def _gamma() -> list[tuple[str, str]]:
    lines = GAMMA_TABLE.read_text(encoding="utf-8").splitlines()
    return [tuple(line.split("|", 1)) for line in lines if line and not line.startswith("#")]  # type: ignore[misc]


#: Gamma's writes this image holds, each a way a reader would make, change or remove something shared.
GAMMA_WRITES = {
    ("can_write", "Dashboard"), ("can_write", "Chart"), ("can_write", "Tag"), ("can_write", "Theme"),
    ("can_tag", "Dashboard"), ("can_tag", "Chart"), ("can_bulk_create", "Tag"),
    ("can_delete_embedded", "Dashboard"), ("can_put_chart_customizations", "Dashboard"),
    ("can_invalidate", "CacheRestApi"), ("can_file_handler", "Superset"),
    ("can_add", "UserRegistrationsRestAPI"), ("can_edit", "UserRegistrationsRestAPI"),
    ("can_delete", "UserRegistrationsRestAPI"),
}  # fmt: skip


def test_the_reader_holds_none_of_gamma_s_writes() -> None:
    gamma = _gamma()
    assert len(gamma) == 95 and GAMMA_WRITES <= set(gamma), "the fixture is Gamma's table as this image makes it"
    reader = set(osprey_roles.reader_permissions(gamma))
    assert reader & GAMMA_WRITES == set(), sorted(reader & GAMMA_WRITES)
    written = {p for p in reader if p[0].split("_")[0] == "can" and p[0] in osprey_roles.WRITES}
    assert written <= osprey_roles.SESSION_STATE, sorted(written - osprey_roles.SESSION_STATE)


def test_the_reader_keeps_every_read_gamma_has() -> None:
    gamma = _gamma()
    reader = set(osprey_roles.reader_permissions(gamma))
    reads = {p for p in gamma if p[0] in ("can_read", "can_list", "can_show", "can_get", "menu_access")}
    assert reads <= reader, sorted(reads - reader)
    assert ("can_read", "Dashboard") in reader and ("can_read", "Chart") in reader


def _config() -> dict[str, object]:
    tree = ast.parse((SUPERSET / "superset_config.py").read_text(encoding="utf-8"))
    return {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in ("AUTH_USER_REGISTRATION_ROLE", "AUTH_ROLES_MAPPING")
    }  # fmt: skip


def test_the_config_maps_the_reports_viewer_and_registers_everyone_as_the_reader() -> None:
    config = _config()
    assert config["AUTH_USER_REGISTRATION_ROLE"] == osprey_roles.READER
    mapping = config["AUTH_ROLES_MAPPING"]
    assert isinstance(mapping, dict) and mapping["reports_viewer"] == [osprey_roles.READER]
    assert all("Gamma" not in roles for roles in mapping.values()), mapping


def test_superset_s_setup_makes_the_reader_from_gamma() -> None:
    setup = (SUPERSET / "osprey_setup.py").read_text(encoding="utf-8")
    setup_tree = ast.parse(setup)
    imported = {a.name for n in ast.walk(setup_tree) if isinstance(n, ast.ImportFrom) and n.module == "osprey_roles"
                for a in n.names}  # fmt: skip
    assert {"READER", "is_reader_permission"} <= imported, imported
    assert "if is_reader_permission(p.permission.name, p.view_menu.name)" in setup
    assert "gamma.permissions" in setup.split("is_reader_permission(p.permission")[0].rsplit("reader.permissions", 1)[1]
    dockerfile = (SUPERSET / "Dockerfile").read_text(encoding="utf-8")
    assert "osprey_roles.py" in dockerfile, "the image carries the roles' rule beside osprey_setup.py"
