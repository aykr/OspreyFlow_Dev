"""ADR-139 Amendment 2 (and Amendment 3, how it was read): the client's own code, in OspreyFlow's
pure arithmetic. No store: `ontology/influencers.py`, the schemas and the weights file.

The golden parity test itself, which loads data and reads it back, is a `GraphPort` conformance case
(`test_client_parity_scores_equal_a_transcription_of_the_clients_r_function`); its transcription of
the R function is `client_r_function.py`. Here:
- the transcription against figures worked by hand;
- **the row shape that does not map exactly**, as a figure: a table mixing kinds;
- order: each composition keeps its own order under its drawing curve (Amendment 2's "Order" test);
- the resolution of the composition and the rarity measure (case, installation, file);
- a dataset trigger the reader cannot read evidences nothing;
- client parity's sum takes adds only;
- the weights file's and the schema's new keys.
"""

from __future__ import annotations

import itertools
import math

import pytest
from pydantic import ValidationError

from ontology.errors import OntologyError
from ontology.influencers import (
    StrengthDefaults,
    connection_strength,
    dataset_evidence,
    load_strength_defaults,
    pair_links,
    parity_drawn,
    parity_strength,
    pre_logistic,
    resolve_settings,
    share_rarity,
)
from ontology.weights import load_weight_rules
from schemas.strength import (
    SHARED_VALUE,
    ActiveInfluencer,
    DatasetTrigger,
    InfluencerTrigger,
    StrengthInfluencer,
)

from .client_r_function import BY_HAND, Row, add_strength_column, client_scores

RULES = load_weight_rules()


def _active(influencer: StrengthInfluencer) -> ActiveInfluencer:
    return ActiveInfluencer(influencer=influencer, layer="installation", version=1)


def test_the_transcription_gives_the_figures_worked_by_hand() -> None:
    """The fixture arithmetic is the R function: each row's figure, worked by hand from
    `1 − N/ΣN + abs_add (+ non_dup_add)`."""
    scores = {(r.dataset, r.source, r.target): v for r, v in client_scores().items()}
    assert scores == pytest.approx(BY_HAND)


def test_a_table_mixing_kinds_is_the_shape_that_does_not_map_exactly() -> None:
    """Amendment 3, said as a figure rather than papered over. In the client's code, `ΣN` is every
    row of the table the function is called on, of every type. One call holding a `dup_phone` row
    (P1 and P2 share ph1) and a direct `call` row (P1 to P3, its own value) gives each row
    `1 − 1/2 = 0.5`. OspreyFlow counts each kind on its own (Amendment 2, ruling 1): the phone is
    the only value of its kind (`1 − 1/1 = 0`), and the call the only link of its type (`1 − 1/1 =
    0`). The two agree only when a call of the function holds one kind; the question is the
    client's."""
    mixed = [
        Row("mixed", "P1", "P2", "dup_phone", "ph1"),
        Row("mixed", "P1", "P3", "call", "call-1"),
    ]
    client = dict(add_strength_column(mixed, "value", 0.0, 0.0))
    assert list(client.values()) == pytest.approx([0.5, 0.5])
    ours_shared = share_rarity(pair_links(2), pair_links(2))
    ours_direct = share_rarity(1, 1)
    assert (ours_shared, ours_direct) == (0.0, 0.0)
    assert client[mixed[0]] != ours_shared and client[mixed[1]] != ours_direct


def test_the_share_rarity_is_the_clients_one_less_n_over_the_sum() -> None:
    """`pair_links` is `C(k, 2)`: three holders stand for three `dup_*` rows, two for one."""
    assert [pair_links(k) for k in range(5)] == [0, 0, 1, 3, 6]
    assert share_rarity(pair_links(3), 6) == pytest.approx(0.5)
    assert share_rarity(0, 6) == 0.0 and share_rarity(1, 0) == 0.0


SUMS = [x / 20 for x in range(-10, 41)]


def test_each_composition_keeps_its_own_order_under_its_drawing() -> None:
    """Amendment 2's order test. Client parity: the drawn strength orders links exactly as their
    raw sums do (the curve is strictly increasing). Standard: the drawn strength orders links as
    their pre-logistic scores with the adds do. Shown red by a curve that folds about its
    midpoint (`s9g_red_parity_order.txt`)."""
    drawn = [parity_drawn(s) for s in SUMS]
    for (a, da), (b, db) in itertools.combinations(zip(SUMS, drawn, strict=True), 2):
        assert (a < b) == (da < db), (a, b)
    boost = _active(StrengthInfluencer(id="b", label="b", link_types=["T"], size=0.3))
    weights = [w / 50 for w in range(1, 50)]
    scored = [
        (pre_logistic(w, RULES) + 0.3, connection_strength(w, "T", [boost], {}, RULES)[0])
        for w in weights
    ]
    for (a, da), (b, db) in itertools.combinations(scored, 2):
        assert (a < b) == (da < db)


def test_client_parity_adds_only_and_ignores_count_and_recency() -> None:
    """The client's sum is the rarity term and the adds; a multiplier, a floor and an exclusion
    have no place in it. Nothing about the link's count or age is an input."""
    kinds = [
        StrengthInfluencer(id="add", label="a", link_types=["T"], size=0.2),
        StrengthInfluencer(id="mul", label="m", link_types=["T"], change="multiply", size=3.0),
        StrengthInfluencer(id="floor", label="f", link_types=["T"], change="floor", size=0.99),
        StrengthInfluencer(id="ex", label="e", link_types=["T"], change="exclude"),
    ]
    raw, drawn, applied = parity_strength(0.75, "T", [_active(i) for i in kinds], {})
    assert raw == pytest.approx(0.95)
    assert drawn == pytest.approx(parity_drawn(0.95))
    assert [a.id for a in applied] == ["add"]
    assert parity_drawn(1.0) == pytest.approx(0.5)


def test_a_dataset_trigger_the_reader_cannot_read_evidences_nothing() -> None:
    """Amendment 2, ruling 3 (rule 3): a dataset-triggered influencer applies to a link evidenced
    in its dataset only when the reader may read that dataset; `None` reads every dataset."""
    by_assaults = _active(StrengthInfluencer(
        id="assaults", label="From assaults", link_types=["T", SHARED_VALUE], size=0.3,
        trigger=DatasetTrigger(datasets=["assaults"]),
    ))  # fmt: skip
    assert dataset_evidence([by_assaults], "T", "assaults", ["assaults"]) == {
        "assaults": "assaults"
    }
    assert dataset_evidence([by_assaults], "T", "assaults", None) == {"assaults": "assaults"}
    assert dataset_evidence([by_assaults], "T", "assaults", ["calls"]) == {}
    assert dataset_evidence([by_assaults], "T", "calls", None) == {}
    assert dataset_evidence([by_assaults], "OTHER", "assaults", None) == {}
    assert dataset_evidence([by_assaults], SHARED_VALUE, "assaults", None) == {
        "assaults": "assaults"
    }


DEFAULTS = StrengthDefaults(influencers=(), rarity_exclude_types=("Alert",))


def test_the_composition_resolves_case_then_installation_then_file() -> None:
    assert resolve_settings(DEFAULTS).composition == "standard"
    assert resolve_settings(DEFAULTS).composition_layer == "file"
    installed = resolve_settings(DEFAULTS, "client_parity", None)
    assert (installed.composition, installed.composition_layer) == ("client_parity", "installation")
    case = resolve_settings(DEFAULTS, "client_parity", "idf", "standard")
    assert (case.composition, case.composition_layer, case.rarity_measure) == (
        "standard", "case", "idf",
    )  # fmt: skip
    # Client parity always reads the client's own measure: its sum is on their scale only so.
    assert resolve_settings(DEFAULTS, None, "idf", "client_parity").rarity_measure == "share"
    assert resolve_settings(DEFAULTS).rarity_measure == "share"


def test_the_weights_file_ships_the_clients_measure_and_the_standard_composition(
    tmp_path: object,
) -> None:
    shipped = load_strength_defaults()
    assert (shipped.rarity_measure, shipped.composition) == ("share", "standard")
    from pathlib import Path

    folder = Path(str(tmp_path))
    bad = folder / "weights.yaml"
    bad.write_text("rarity:\n  measure: entropy\n", encoding="utf-8")
    with pytest.raises(OntologyError, match="share"):
        load_strength_defaults(bad)
    bad.write_text("composition: clients\n", encoding="utf-8")
    with pytest.raises(OntologyError, match="client_parity"):
        load_strength_defaults(bad)


def test_an_influencer_on_shared_values_is_triggered_by_a_dataset_or_nothing() -> None:
    """A shared value is a path, not a stored link: no record evidences it, and the client's
    `dup_*` rows take only `abs_add`."""
    record = InfluencerTrigger(entity_type="Incident", property="category", values=["assault"])
    with pytest.raises(ValidationError, match="dataset"):
        StrengthInfluencer(id="x", label="x", link_types=[SHARED_VALUE], size=0.1, trigger=record)
    with pytest.raises(ValidationError, match="added boost"):
        StrengthInfluencer(id="x", label="x", link_types=[SHARED_VALUE], change="floor", size=0.5)
    ok = StrengthInfluencer(
        id="x", label="x", link_types=[SHARED_VALUE], size=0.1,
        trigger=DatasetTrigger(datasets=["phones"]),
    )  # fmt: skip
    assert ok.trigger is not None and ok.trigger.kind == "dataset"
    # A trigger stored before Amendment 2 (no `kind`) still reads as a record trigger.
    old = StrengthInfluencer.model_validate({
        "id": "i", "label": "i", "link_types": ["T"], "size": 0.1,
        "trigger": {"entity_type": "Incident", "property": "category", "values": ["assault"]},
    })  # fmt: skip
    assert isinstance(old.trigger, InfluencerTrigger)
    assert math.isclose(old.size, 0.1)
