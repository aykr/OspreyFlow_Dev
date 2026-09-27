"""Connect-stage schemas — `docs/09_INGEST_STUDIO.md` §2 (the connector
catalogue and the three mandatory gate questions) and §6 (the
`studio_recipes` draft shape)."""

from __future__ import annotations

from schemas.ingest import (
    CONNECTOR_CATALOGUE,
    ConnectDraftInput,
    StudioRecipeDraft,
    StudioRecipeStatus,
)


def test_the_catalogue_names_every_group_from_the_spec() -> None:
    groups = {entry.group for entry in CONNECTOR_CATALOGUE}
    assert groups == {
        "Communications",
        "Mobile device",
        "Financial",
        "Vehicle and movement",
        "Records",
        "Generic",
        "Documents",
        "Images",
        "Audio and video",
        "Archives",
    }


def test_availability_is_derived_from_the_profile_files_not_declared(tmp_path) -> None:
    """**Round 13bf replaced the instance assertion with the mechanism one.** This test used to
    read `assert available_ids == {"generic-csv"}` — true at the time, and a tripwire the moment
    a second connector was built, which is exactly what happened. Pinning the *rule* instead means
    it stays correct as layouts are added, and still fails if availability ever goes back to being
    a literal.

    The rule (`09_INGEST_STUDIO.md` §2): a connector is available iff a `connectors/<id>.yaml`
    profile exists naming a reader this codebase implements. Nothing declares it.
    """
    from schemas.connectors import ConnectorProfile
    from schemas.ingest import connector_catalogue

    (tmp_path / "generic-csv.yaml").write_text(
        ConnectorProfile(
            id="generic-csv", label="CSV", group="Generic", reader="csv"
        ).model_dump_json(),
        encoding="utf-8",
    )
    # A profile naming a reader that does not exist: parsed, listed, and **unavailable** — the
    # catalogue shows the gap rather than hiding the row.
    (tmp_path / "comms-cdr-ipdr.yaml").write_text(
        ConnectorProfile(
            id="comms-cdr-ipdr", label="CDR", group="Communications", reader="not-implemented"
        ).model_dump_json(),
        encoding="utf-8",
    )

    catalogue = connector_catalogue(tmp_path)
    by_id = {entry.id: entry for entry in catalogue}
    assert by_id["generic-csv"].available is True
    assert by_id["comms-cdr-ipdr"].available is False, (
        "a profile naming an unimplemented reader was reported available, so the Studio would "
        "offer a connector nothing can read"
    )
    assert by_id["generic-tsv"].available is False, (
        "a declared entry with no profile file was reported available"
    )
    assert "generic-tsv" in by_id, "an entry with no profile vanished — the gap must stay visible"


def test_the_shipped_profiles_make_the_cdr_layout_available() -> None:
    """The instance, asserted separately from the rule above. `08_ACCEPTANCE_SCENARIOS.md` B1-B3
    need `cdr-generic-csv`, and before round 13bf it was declared in §2's own catalogue and
    refused by the Studio — the gap REPORT-13bc measured."""
    by_id = {entry.id: entry for entry in CONNECTOR_CATALOGUE}
    assert by_id["cdr-generic-csv"].available is True
    assert by_id["generic-csv"].available is True


def test_catalogue_ids_are_unique() -> None:
    ids = [entry.id for entry in CONNECTOR_CATALOGUE]
    assert len(ids) == len(set(ids))


def _draft(**overrides: object) -> StudioRecipeDraft:
    base: dict[str, object] = {
        "recipe_id": "recipe-1",
        "version": 1,
        "status": StudioRecipeStatus.DRAFT,
        "label": "Carrier A — CDR",
        "owning_unit": "unit-1",
        "created_by": "analyst-1",
        "created_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return StudioRecipeDraft(**base)  # type: ignore[arg-type]


#: A `Handling` needs `classification`, `handling_code`, `originator` and
#: `owning_unit` (`schemas.domain.Handling`) — this is the smallest dict
#: that actually constructs one, used wherever a test needs a *complete*
#: handling marking rather than a merely non-empty one.
_COMPLETE_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


def test_ready_for_profile_is_false_until_all_three_gate_answers_are_set() -> None:
    assert _draft().ready_for_profile is False
    assert _draft(source_location="s3://bucket/carrier-a.csv").ready_for_profile is False
    assert (
        _draft(
            source_location="s3://bucket/carrier-a.csv",
            handling={"classification": "OFFICIAL", "handling_code": "P"},
        ).ready_for_profile
        is False
    )


def test_ready_for_profile_is_true_once_all_three_are_set() -> None:
    draft = _draft(
        source_location="s3://bucket/carrier-a.csv",
        handling=_COMPLETE_HANDLING,
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
    )
    assert draft.ready_for_profile is True


def test_ready_for_profile_stays_false_with_a_non_empty_but_incomplete_handling_marking() -> None:
    """A non-empty `handling` dict used to be enough on its own — but
    `{"classification": "OFFICIAL"}` alone can't build a `schemas.domain.
    Handling` (`handling_code`/`originator`/`owning_unit` are also
    required), and `services/api/studio_profile.py`'s `profile_recipe_source`
    needs a real one to mask against. This is what keeps a draft from ever
    reaching Profile in a state Profile itself would then reject — a draft
    this test's shape describes can no longer call itself `ready_for_profile`
    (`tests/services/api/test_studio_recipe_routes.py`'s
    `test_get_profile_defends_against_a_bypassed_ready_for_profile_flag`
    is the corresponding proof that Profile's own check still stands guard
    for a caller that reaches it some other way)."""
    for incomplete in (
        {"classification": "OFFICIAL"},
        {"classification": "OFFICIAL", "handling_code": "P"},
        {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1"},
    ):
        draft = _draft(
            source_location="s3://bucket/carrier-a.csv",
            handling=incomplete,
            legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
        )
        assert draft.ready_for_profile is False, incomplete


def test_ready_for_profile_is_serialised_on_the_model() -> None:
    """`@computed_field`, not a Python-only `@property` — the Connect
    screen (and the generated TS type) need this in the JSON response."""
    draft = _draft(
        source_location="s3://bucket/carrier-a.csv",
        handling=_COMPLETE_HANDLING,
        legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
    )
    assert draft.model_dump()["ready_for_profile"] is True


def test_connect_draft_input_only_requires_label_and_connector() -> None:
    draft_input = ConnectDraftInput(label="Carrier A — CDR", connector_profile="generic-csv")
    assert draft_input.source_location is None
    assert draft_input.legal_basis is None
    assert draft_input.handling == {}
