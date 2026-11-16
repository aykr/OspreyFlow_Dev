"""`OspreyReader`, the Superset role of a Reports Viewer and of every account at registration:
Superset's Gamma less every write (the owner's ruling, 16 November 2026; `superset_config.py` maps
the Reports Viewer to it and makes it `AUTH_USER_REGISTRATION_ROLE`, which Flask-AppBuilder adds
to every account).

Gamma is not read-only: in this image it holds `can_write` on Dashboard, Chart, Tag and Theme,
tagging, removing a board's embedding, the chart customisations, a cache's invalidation, file
handling and the user registrations' writes (`tests/fixtures/superset/gamma_permissions.txt`, its
table as `superset init` makes it). A Reports Viewer saved a dashboard in v0.6.0's package test.

Default-deny: every permission named for a write is left out, but for the few that keep a person's
own session's state, named in `SESSION_STATE` with what each is for. A write a later Superset
gives Gamma is left out until someone names it here. Pure, so `tests/test_superset_reader_role.py`
holds it to Gamma's own table; `osprey_setup.py` applies it at every start."""

from __future__ import annotations

from collections.abc import Iterable

READER = "OspreyReader"

#: Permission names that make, change or remove something: Flask-AppBuilder's and Superset's own.
WRITES = frozenset({
    "can_write", "can_add", "can_edit", "can_delete", "can_post", "can_put", "can_save", "can_copy",
    "can_import", "can_tag", "can_bulk_create", "can_delete_embedded", "can_set_embedded",
    "can_put_chart_customizations", "can_invalidate", "can_file_handler", "can_warm_up_cache",
    "can_this_form_post",
})  # fmt: skip

#: The writes a reader keeps: each the person's own session's state, never shared content.
SESSION_STATE = frozenset({
    ("can_write", "DashboardFilterStateRestApi"),  # a board's native filters, as they set them
    ("can_write", "DashboardPermalinkRestApi"),  # a link to the board as they see it, to share
    ("can_write", "ExploreFormDataRestApi"),  # a chart's form while they look at it
    ("can_write", "ExplorePermalinkRestApi"),  # a link to that view of a chart
    ("can_write", "CurrentUserRestApi"),  # their own preferences
})  # fmt: skip


def is_reader_permission(name: str, view: str) -> bool:
    return name not in WRITES or (name, view) in SESSION_STATE


def reader_permissions(gamma: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Gamma's (permission, view) pairs a reader holds."""
    return [(name, view) for name, view in gamma if is_reader_permission(name, view)]
