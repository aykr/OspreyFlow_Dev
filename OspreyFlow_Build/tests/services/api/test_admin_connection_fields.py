"""Admin › Connections' fields, L2.7 (`06_DECISIONS.md` ADR-140 Amendments 13 and 15): a connection
names its secret and never carries its value, so no route answers one. `test_connector_routes.py`
(studio-b's L1.6) holds the list, the Studio's list, a registration, *Refresh now* and the audit to
that. This file adds the refusal: an administrator who pastes the secret's value into the field
for its name, or into any field the schema refuses, is told which field is wrong and never shown
what they sent, since FastAPI's own 422 carries each refused input back.

What a mistake would do, and the case that catches it (each shown red at its call site,
`process/lanes/admin/L2.7_RED_RECORD.md`):

- a refused value answered back (the route's body read by FastAPI again):
  `test_a_refused_connection_never_answers_what_was_sent`.
"""

# ruff: noqa: F811 - `world` is the fixture, taken by name
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from tests.services.api.test_connector_routes import (
    API,
    TOKEN,
    _as,
    world,  # noqa: F401 - the fixture, by name
)

#: Each field an administrator could paste the value into, with the field the refusal names.
PASTED: list[tuple[str, dict[str, Any], str]] = [
    ("into the secret's name", {"secret": TOKEN}, "secret"),
    ("as a field of its own", {"password": TOKEN}, "password"),
    ("into the base URL", {"base_url": TOKEN}, "base_url"),
]


@pytest.mark.parametrize(("where", "settings", "field"), PASTED, ids=[p[0] for p in PASTED])
def test_a_refused_connection_never_answers_what_was_sent(
    world: SimpleNamespace, where: str, settings: dict[str, Any], field: str
) -> None:
    """Refused as a 422 naming the field, with neither the value nor any other value sent in the
    answer, the audit or the store. Red with the body read by FastAPI (its 422 echoes `input`)."""
    body = {**API, "settings": {**API["settings"], **settings}}
    answer = world.client.post("/v1/admin/connections", json=body, headers=_as("admin"))
    assert answer.status_code == 422, answer.text
    assert TOKEN not in answer.text, where
    assert field in answer.json()["detail"]["detail"], answer.text
    assert answer.json()["detail"]["error"] == "connection_refused"
    assert TOKEN not in json.dumps(world.audit.entries, default=str)


def test_a_connection_is_still_named_with_its_fields(world: SimpleNamespace) -> None:
    """The same body, with the secret named rather than pasted, is kept: the route reads every field
    the screen sends, and answers the secret's name alone."""
    made = world.client.post("/v1/admin/connections", json=API, headers=_as("admin"))
    assert made.status_code == 201, made.text
    assert made.json()["settings"]["secret"] == "TELCO"
    assert TOKEN not in made.text
