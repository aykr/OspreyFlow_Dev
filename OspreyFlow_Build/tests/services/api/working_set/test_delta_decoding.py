"""Stored deltas written before ADR-124 still decode (decision 1).

`filtered_count` left `DeltaSnapshot`, and `merged`, `split` and `affected` left `DeltaReproject`.
The delta stream holds entries a deployment wrote before the change, and `decode_delta` reads them
back for a reconnect and for the live push. The models ignore extra fields, so an old entry parses
and its figures are not read; a model that began refusing them would turn every reconnect across
the upgrade into an error. `DeltaNotice` was never appended to the stream, so its leaving needs no
such case; a notice is simply no longer a delta.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from services.api.working_set.models import (
    DeltaReproject,
    DeltaSnapshot,
    ExpansionOutcome,
    decode_delta,
)


def test_a_stored_snapshot_carrying_filtered_count_decodes() -> None:
    delta = decode_delta(
        {"seq": 4, "op": "snapshot", "nodes": [], "edges": [], "filtered_count": 7}
    )

    assert isinstance(delta, DeltaSnapshot)
    assert delta.seq == 4
    assert "filtered_count" not in delta.model_dump()


def test_a_stored_reproject_carrying_the_actors_figures_decodes() -> None:
    delta = decode_delta(
        {
            "seq": 5,
            "op": "reproject",
            "reason": "resolution threshold changed from 0.95 to 0.8",
            "merged": 3,
            "split": 1,
            "affected": 47,
            "affected_cluster_ids": {"n1": "c1"},
        }
    )

    assert isinstance(delta, DeltaReproject)
    assert delta.affected_cluster_ids == {"n1": "c1"}
    assert {"merged", "split", "affected"} & set(delta.model_dump()) == set()


def test_an_expansion_outcome_stored_with_filtered_count_parses() -> None:
    outcome = ExpansionOutcome.model_validate(
        {"delta": {"seq": 1, "op": "add", "nodes": [], "edges": []}, "filtered_count": 2}
    )

    assert "filtered_count" not in outcome.model_dump()


def test_a_notice_is_no_longer_a_delta() -> None:
    """Violation caught: `notice` still decodes, so a stale producer's withheld count would be
    accepted as a delta and forwarded to every socket."""
    with pytest.raises(ValidationError):
        decode_delta({"seq": 1, "op": "notice", "message": "1 item(s) withheld", "count": 1})
