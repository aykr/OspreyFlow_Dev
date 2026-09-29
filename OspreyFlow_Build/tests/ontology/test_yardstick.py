"""Probability-yardstick loader — `spec/01_DOMAIN_MODEL.md` §5, Phase 8 Stage 4b."""

from __future__ import annotations

import pytest

from ontology.errors import YardstickError
from ontology.yardstick import load_phia_yardstick, load_yardstick


def test_phia_yardstick_loads_with_its_seven_named_bands() -> None:
    """`01_DOMAIN_MODEL.md` §5's own worked example — the shipped file must match it exactly, not
    merely load without error."""
    yardstick = load_phia_yardstick()
    assert yardstick.name == "PHIA probabilistic yardstick"
    assert yardstick.labels() == [
        "remote chance",
        "highly unlikely",
        "unlikely",
        "realistic possibility",
        "likely",
        "highly likely",
        "almost certain",
    ]
    almost_certain = yardstick.bands[-1]
    assert almost_certain.lower == 0.95
    assert almost_certain.upper == 1.00


def test_a_revision_is_a_config_change(tmp_path) -> None:
    """§5's own claim: "a revision is a config change" — a differently-shaped yardstick file loads
    with no code change, proving the loader is generic over the YAML, not hardcoded to `phia.yaml`'s
    own bands."""
    custom = tmp_path / "custom.yaml"
    custom.write_text(
        "name: Custom Org Yardstick\n"
        "bands:\n"
        "  - {label: low, lower: 0.0, upper: 0.3}\n"
        "  - {label: high, lower: 0.7, upper: 1.0}\n"
    )
    yardstick = load_yardstick(custom)
    assert yardstick.name == "Custom Org Yardstick"
    assert yardstick.labels() == ["low", "high"]


def test_a_malformed_yardstick_raises_yardstick_error(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: {a: valid, yardstick: shape}\n")
    with pytest.raises(YardstickError):
        load_yardstick(bad)


def test_a_non_mapping_yardstick_file_raises_yardstick_error(tmp_path) -> None:
    bad = tmp_path / "bad_list.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(YardstickError):
        load_yardstick(bad)
