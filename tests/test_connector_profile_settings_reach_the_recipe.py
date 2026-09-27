"""A connector profile's own settings must survive the Studio — round 13bf.

**The defect this exists to hold down, in the shape it actually took.** `studio_verify` and
`studio_publish` both built their `RecipeConnector` as

    RecipeConnector(profile=draft.connector_profile or "generic-csv")

— the profile's *id* and nothing else. Every other field of that model has a default, so the call
type-checked, linted, passed every existing test, and produced a recipe whose `date_order` was
`None` no matter what the analyst's chosen layout declared. `connectors/cdr-generic-csv.yaml`
says `date_order: dmy`; the recipe published from it said nothing at all, and
`08_ACCEPTANCE_SCENARIOS.md` B3's own `12/01/2026` would have been read with no declared order.

Nothing was mis-implemented against its own tests. The tests asserted on a recipe built in-process
with a hand-written `RecipeConnector`, which carried the settings because the test author put them
there — so the tests measured a connector the Studio never builds. That is `CLAUDE.md` rule 15's
second worked example with the roles swapped: not a fixture more permissive than the real
dependency, but a test input more complete than the real producer.

**So these assert through `build_recipe`** — the real call site, on a real profile file — rather
than on a `RecipeConnector` this module constructs. Rule 15: the planted violation must take the
shape the code under test actually emits at its own call site. Reverting `connector_for` to the
old one-argument call turns `test_a_layouts_declared_date_order_survives_publish` red and leaves
the rest of the suite green, which is the point: it was the only thing watching.

Rule 12, named plainly — if the invariant "a connector profile's settings reach the engine" is
ever violated again, *this file* is what fails.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.studio_profile import (
    ConnectorNotAvailableError,
    connector_for,
    require_available_connector,
)
from services.api.studio_publish import build_recipe

from schemas.connectors import load_connector_profiles
from schemas.ingest import (
    CONNECTORS_DIR,
    FieldBinding,
    RecipeEntity,
    RowTemplate,
    StudioRecipeDraft,
    StudioRecipeStatus,
)

_HANDLING = {
    "classification": "OFFICIAL-SENSITIVE",
    "handling_code": "UK_EYES_ONLY",
    "originator": "Test Force",
    "owning_unit": "Test Unit",
}


def _draft(connector_profile: str | None) -> StudioRecipeDraft:
    """A verified draft, exactly as `build_recipe`'s own caller hands it over."""
    return StudioRecipeDraft(
        recipe_id="r-13bf",
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="round 13bf",
        connector_profile=connector_profile,
        source_location="/tmp/unused.csv",
        handling=_HANDLING,
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
        owning_unit="Test Unit",
        created_by="tester",
        created_at=datetime.now(UTC),
        ready_for_profile=True,
        row_template=RowTemplate(
            entities=[
                RecipeEntity(
                    ref="a",
                    key="a",
                    pole_class="object",
                    type="Identifier",
                    match_on="value_normalised",
                    on_match="reference",
                    properties={
                        "value_normalised": FieldBinding(field="a_party"),
                        "endpoint_kind": FieldBinding(literal="msisdn"),
                    },
                )
            ]
        ),
        unmapped_fields=[],
    )


def test_a_layouts_declared_date_order_survives_publish() -> None:
    """**The regression test for the defect above.**

    `cdr-generic-csv` declares `date_order: dmy` because a CDR export of a UK carrier writes
    `12/01/2026` for the twelfth of January. If that declaration does not reach the published
    recipe, the engine reads it as the first of December and every call in the fixture lands in
    the wrong month — silently, with no error anywhere, which is precisely what makes it worth a
    test rather than a comment.
    """
    profile = load_connector_profiles(CONNECTORS_DIR)["cdr-generic-csv"]
    assert profile.date_order == "dmy", "fixture precondition: the profile declares an order"

    recipe = build_recipe(
        _draft("cdr-generic-csv"), ontology_version=1, schedule_cron=None, schedule_watch=None
    )

    assert recipe.connector.date_order == "dmy"
    assert recipe.connector.profile == "cdr-generic-csv"


def test_every_declared_setting_of_a_profile_reaches_the_recipe() -> None:
    """The generalisation, so a *newly added* connector-level setting cannot be forgotten.

    `connector_for` copies field by field. A field added to `ConnectorProfile` and to
    `RecipeConnector` but not to the copy would leave exactly the same silent hole this file
    exists for — and would pass the `date_order` test above, which only watches one field. This
    compares every name the two models share, so the next setting is covered by construction
    rather than by whoever adds it remembering to come back here.
    """
    profile = load_connector_profiles(CONNECTORS_DIR)["cdr-generic-csv"]
    connector = connector_for(_draft("cdr-generic-csv"))

    shared = (set(type(profile).model_fields) & set(type(connector).model_fields)) - {"profile"}
    assert shared, "the two models share settings; if not, this test has stopped meaning anything"
    for name in sorted(shared):
        assert getattr(connector, name) == getattr(profile, name), (
            f"{name!r} is declared on the connector profile but does not reach the recipe"
        )


def test_publish_refuses_a_draft_with_no_connector_profile() -> None:
    """The other half of the same line. `or "generic-csv"` did not merely lose settings — it
    substituted a *different layout's* settings for the analyst's own, so a draft that had somehow
    reached Publish without a connector was published as a plain comma-separated file with no date
    order. Refused by name now; there is no default connector."""
    with pytest.raises(ConnectorNotAvailableError):
        build_recipe(_draft(None), ontology_version=1, schedule_cron=None, schedule_watch=None)


def test_publish_refuses_a_connector_with_no_profile_file() -> None:
    with pytest.raises(ConnectorNotAvailableError):
        build_recipe(
            _draft("no-such-carrier"), ontology_version=1, schedule_cron=None, schedule_watch=None
        )


def test_the_stages_cannot_disagree_about_which_connectors_are_available() -> None:
    """Map, Verify and Publish all gate on `require_available_connector`, so there is one answer.

    Round 13bf found four independent answers to this one question — `_AVAILABLE_CONNECTORS` in
    `studio_profile`, an inline `{"generic-csv"}` in `studio_map.row_template`, another in
    `studio_verify.verify_recipe`, and the catalogue's own `available` flag. Adding
    `cdr-generic-csv` to one left the others refusing it, which is how `08`'s B1-B3 came to be
    unwalkable through the analyst's own door while every in-process test passed.

    This asserts the *derivation*, not a list: a profile file that exists and names an implemented
    reader is available, and nothing else is.
    """
    profiles = load_connector_profiles(CONNECTORS_DIR)
    assert "cdr-generic-csv" in profiles and "generic-csv" in profiles

    for identifier, profile in profiles.items():
        if profile.available:
            assert require_available_connector(_draft(identifier)) is not None
        else:
            with pytest.raises(ConnectorNotAvailableError):
                require_available_connector(_draft(identifier))


def test_the_recipe_repository_root_has_exactly_one_source() -> None:
    """**The third copy of one fact, found one layer in from the one this round started on.**

    Publishing commits to a git repository (`09_INGEST_STUDIO.md` §6). Where that repository is
    was computed independently in three places: `studio_publish._REPO_ROOT`, the renderer's
    `OSPREY_RECIPE_REPO_ROOT`, and `services/api/app.py`'s own `_RECIPES_REPO_ROOT` — and the
    third is the one the route actually passes.

    That is why this test exists rather than a comment. Setting the environment variable moved the
    first two and left the third at `/app`; Publish then returned **200** and wrote the record
    into the image's own code directory, where the next `docker compose up --build` discards it.
    A fix that reports success while changing nothing is worse than the failure it replaced, and
    the only thing that distinguished them was looking in the container afterwards.

    Asserting identity rather than equality is deliberate: two constants that happen to agree
    today because both call `.parents[2]` would satisfy `==` and diverge the moment either is
    configured, which is precisely what happened.
    """
    from services.api import app as app_module
    from services.api import studio_publish

    assert app_module._RECIPES_REPO_ROOT is studio_publish._REPO_ROOT, (
        "services/api/app.py computes the recipe repository root independently of "
        "services/api/studio_publish.py, so configuring one leaves the other pointing elsewhere"
    )
