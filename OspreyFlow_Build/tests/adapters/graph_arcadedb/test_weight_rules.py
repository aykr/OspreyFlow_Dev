"""Per-type link weights and the weights file — ADR-120 D3, `01_DOMAIN_MODEL.md` §6.1.

Pure: nothing here opens a store. Each test names the defect it catches (rule 12), and the
ones that guard the same-pair invariant also prove they can fail (rule 15): the pair grid with the
old formula, the self-loop series with its mutual-information term left in.

- `test_the_weights_file_derives_midpoint_and_scale_for_every_version` catches a version whose
  `midpoint` and `scale` were tuned by hand instead of derived from alpha and beta, which would
  make one type's heavy count draw thicker than another's.
- `test_version_one_carries_the_brief_s_rules` catches a rule, a unit or a heavy count in version
  one that differs from the table the owner approved.
- `test_no_earlier_version_of_the_weights_file_is_edited` catches an old version rewritten in
  place against a frozen copy, which would silently recalibrate every weight stored under it;
  `test_the_history_check_reports_an_edited_version` plants such an edit and shows the check
  reports it, and that an appended version and a removed one are told apart.
- `test_the_loader_refuses_versions_out_of_order` and
  `test_the_loader_refuses_a_midpoint_that_is_not_derived` catch a loader that accepts a file
  whose history is not 1..n in order, or whose calibration is not the derived one, or that
  refuses it without naming the version and the field.
- `test_the_loader_refuses_a_malformed_rule_naming_the_field` catches a loader that accepts a rule
  setting both or neither of `heavy` and `fixed`, a `heavy` below 1 or a `fixed` outside (0, 1],
  or refuses it without naming the version and the field.
- `test_adding_occurrences_to_one_pair_never_lowers_its_weight` catches a formula under which one
  more occurrence of the same pair, the rest of the corpus and the recency unchanged, lowers the
  weight (raw PMI did); `test_the_grid_would_catch_raw_pmi_under_the_count_term` plants the old
  formula and shows the same grid reports it. The grid's self-loop series is computed with the
  self-loop's mutual-information term at 0 (ADR-120 Amendment 4).
- `test_a_self_loop_s_mutual_information_term_is_zero` catches a self-loop whose weight still
  takes the pair's mutual information, or one that is not told it is a self-loop, or a structural
  self-loop that stops weighing its strength;
  `test_the_grid_would_catch_a_self_loop_given_its_pmi` computes that term by hand on the same
  series and shows the series reports a decrease, so its green is not a series that cannot fail.
- `test_npmi_is_bounded_and_defined_at_every_edge_case` catches a division by zero where
  p(u,v) = 1, a value outside [-1, 1] on a self-loop, and a non-zero value where the corpus has no
  total, pair or degree.
- `test_a_counted_type_s_heavy_count_draws_at_the_logistic_of_two` and
  `test_one_occurrence_draws_at_its_formula_value` catch a calibration that is not the derived
  one, or a count term that is not divided by the type's own heavy count.
- `test_a_structural_type_weighs_its_strength_whatever_its_occurrences` catches a fixed rule that
  still follows its occurrences, recency or mutual information.
- `test_an_unlisted_type_takes_the_default_rule` and
  `test_the_parameter_set_names_the_version_and_the_rule` catch a type with no rule failing, or
  a parameter set that does not name the version and rule a weight was computed under.
- ADR-123 (a link's weight comes from the link alone):
  `test_version_two_loads_with_gamma_0_and_version_one_s_other_values` catches a version 2 whose
  gamma is not 0 or whose other values are not version 1's;
  `test_a_version_after_one_with_a_gamma_other_than_0_is_refused_naming_it` catches a loader that
  takes a later version with gamma other than 0 (refused naming the version and the field, with a
  positive control that differs only in gamma);
  `test_under_version_two_a_link_s_weight_is_the_same_whatever_its_corpus_counts` catches any
  corpus count reaching a weight, over the pair grid, and proves the same assertion fails under
  version 1 (rule 15);
  `test_the_grid_through_the_weight_would_catch_a_self_loop_not_told_it_is_one` plants the missing
  `self_loop` flag through `compute_weight` itself and shows version 1 reports it and version 2
  cannot; `test_version_two_keeps_the_calibration_and_weighs_its_count_and_recency_alone` catches a
  version 2 whose calibration drifted from version 1's.
- Which tests are pinned to version 1 (`_rules(1)`, by index, not "latest"), because they need the
  mutual-information term (gamma 0.3) to be able to fail, and which run under both versions:
  - Pinned to version 1: `test_a_self_loop_s_mutual_information_term_is_zero`,
    `test_the_grid_through_the_weight_would_catch_a_self_loop_not_told_it_is_one` (its version 1
    half), `test_under_version_two_a_link_s_weight_is_the_same_whatever_its_corpus_counts` (its
    version 1 half) and `test_version_one_carries_the_brief_s_rules` (by index). The two grid
    plants that compute the formula by hand
    (`test_the_grid_would_catch_raw_pmi_under_the_count_term` and
    `test_the_grid_would_catch_a_self_loop_given_its_pmi`) and
    `test_npmi_is_bounded_and_defined_at_every_edge_case` take no rules, so are version 1's
    constants by construction.
  - Run under both versions (`weights_version` 1 and 2):
    `test_adding_occurrences_to_one_pair_never_lowers_its_weight`,
    `test_a_counted_type_s_heavy_count_draws_at_the_logistic_of_two`,
    `test_one_occurrence_draws_at_its_formula_value`,
    `test_a_structural_type_weighs_its_strength_whatever_its_occurrences`,
    `test_an_unlisted_type_takes_the_default_rule`,
    `test_the_parameter_set_names_the_version_and_the_rule` and
    `test_on_a_star_the_heavy_links_outweigh_a_one_off_cell_share_and_the_picture`.
- `test_on_a_star_the_heavy_links_outweigh_a_one_off_cell_share_and_the_picture` catches a
  formula that draws the principal's one-off links as heavy as the coordinator's calls.
"""

from __future__ import annotations

import copy
import functools
import itertools
import math
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from schemas.domain import WeightComponents

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
FROZEN = Path(__file__).resolve().parent / "fixtures" / "weights_v1.yaml"

#: The brief's table: type -> (unit, heavy) for a counted rule.
COUNTED = {
    "SHARED_CELL_WITH": ("one week shared", 12),
    "VISITED": ("one visit", 8),
    "COMMUNICATED_WITH": ("one call", 40),
    "TRANSACTED": ("one transfer", 6),
    "MENTIONED_IN": ("one report", 3),
    "ROLE_IN": ("one incident", 3),
    "IN_CONFLICT_WITH": ("one episode", 2),
}
#: type -> fixed strength.
FIXED = {
    "CO_DEFENDANT_OF": 0.75,
    "FAMILY_OF": 0.75,
    "MEMBER_OF": 0.75,
    "HELD_AT": 0.75,
    "DEPICTS": 0.2,
}
DEFAULT_UNIT = ("one occurrence", 10)
#: A type the weights file does not name, so it takes the default rule.
UNLISTED = "USES"
LOGISTIC_OF_TWO = 1.0 / (1.0 + math.exp(-2.0))


def _weights_path() -> Path:
    import ontology

    return Path(ontology.__file__).resolve().parent / "weights" / "default.yaml"


def _raw_versions(path: Path) -> list[dict[str, Any]]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    versions = loaded["versions"]
    assert isinstance(versions, list)
    return [v for v in versions if isinstance(v, dict)]


def _write_versions(path: Path, versions: Sequence[dict[str, Any]]) -> Path:
    path.write_text(yaml.safe_dump({"versions": list(versions)}), encoding="utf-8")
    return path


def _edited_versions(
    frozen: Sequence[dict[str, Any]], history: Sequence[dict[str, Any]]
) -> list[int]:
    """The versions in `frozen` that `history` no longer holds as they were: edited, or removed.
    A version in `history` that `frozen` does not hold is an append, which is allowed."""
    current = {int(v["version"]): v for v in history}
    return sorted(int(v["version"]) for v in frozen if current.get(int(v["version"])) != v)


#: The weights versions the cases that do not depend on the mutual-information term run under.
VERSIONS = pytest.mark.parametrize("weights_version", [1, 2])


@functools.cache
def _rules(version: int = 1) -> Any:
    """A version of the weights file, by index and not "latest" (ADR-123). Version 1 (gamma 0.3) is
    the one the mutual-information cases are pinned to, so each still exercises the term and can
    still fail; version 2 (gamma 0) is the other the unpinned cases run under."""
    from ontology.weights import load_weight_history

    rules = load_weight_history()[version - 1]
    assert rules.version == version
    assert rules.gamma == (0.3 if version == 1 else 0.0)
    return rules


def _rules_v2() -> Any:
    return _rules(2)


def _components(
    occurrences: int,
    *,
    source_degree: int,
    target_degree: int,
    total: int,
    pair: int | None = None,
) -> WeightComponents:
    return WeightComponents(
        occurrences=occurrences,
        corpus_pair_count=occurrences if pair is None else pair,
        corpus_source_degree=source_degree,
        corpus_target_degree=target_degree,
        corpus_total_occurrences=total,
        computed_at=NOW,
    )


def _independent(occurrences: int) -> WeightComponents:
    """A pair whose mutual-information term is exactly zero: p(u,v) = p(u)·p(v), with each end's
    degree twice the pair's and a total four times it."""
    return _components(
        occurrences,
        source_degree=2 * occurrences,
        target_degree=2 * occurrences,
        total=4 * occurrences,
    )


def _weigh(
    components: WeightComponents,
    edge_type: str,
    *,
    valid_to: datetime | None,
    self_loop: bool,
    rules: Any,
) -> float:
    from adapters.graph_arcadedb.weight import compute_weight

    return compute_weight(
        components,
        edge_type=edge_type,
        valid_to=valid_to,
        now=NOW,
        rules=rules,
        self_loop=self_loop,
    )


# --- the weights file ---------------------------------------------------------


def test_the_weights_file_derives_midpoint_and_scale_for_every_version() -> None:
    """Catches a version whose `midpoint` and `scale` are not the derived ones."""
    versions = _raw_versions(_weights_path())
    assert versions
    for version in versions:
        assert version["scale"] == pytest.approx(version["alpha"] / 3, abs=1e-12)
        assert version["midpoint"] == pytest.approx(
            version["beta"] + version["alpha"] / 3, abs=1e-12
        )


def test_version_one_carries_the_brief_s_rules() -> None:
    """Catches a rule, unit or heavy count that is not in the owner's table, in the raw file and
    as the loader and `rule_for` give it."""
    from ontology.weights import load_weight_history

    raw = _raw_versions(_weights_path())[0]
    assert raw["version"] == 1
    assert (raw["alpha"], raw["beta"], raw["gamma"], raw["half_life_days"]) == (0.5, 0.2, 0.3, 90)
    assert (raw["default"]["unit"], raw["default"]["heavy"]) == DEFAULT_UNIT
    assert set(raw["rules"]) == set(COUNTED) | set(FIXED)
    for name, (unit, heavy) in COUNTED.items():
        assert raw["rules"][name] == {"unit": unit, "heavy": heavy}, name
    for name, strength in FIXED.items():
        assert raw["rules"][name] == {"fixed": strength}, name

    one = load_weight_history()[0]
    assert one.version == 1
    assert (one.alpha, one.beta, one.gamma, one.half_life_days) == (0.5, 0.2, 0.3, 90)
    assert one.midpoint == pytest.approx(0.2 + 0.5 / 3, abs=1e-12)
    assert one.scale == pytest.approx(0.5 / 3, abs=1e-12)
    for name, (_, heavy) in COUNTED.items():
        rule_name, rule = one.rule_for(name)
        assert (rule_name, rule.heavy, rule.fixed) == (name, heavy, None)
    for name, strength in FIXED.items():
        rule_name, rule = one.rule_for(name)
        assert (rule_name, rule.heavy, rule.fixed) == (name, None, strength)
    rule_name, rule = one.rule_for(UNLISTED)
    assert (rule_name, rule.heavy, rule.fixed) == ("default", 10, None)


def test_no_earlier_version_of_the_weights_file_is_edited() -> None:
    """Catches version 1 or 2 of the real file differing from the frozen copy, or the real file
    lacking version 2 (ADR-123); an appended version 3 is allowed and reported by nothing."""
    frozen = _raw_versions(FROZEN)
    assert [v["version"] for v in frozen] == [1, 2]
    assert frozen[1]["gamma"] == 0
    assert _edited_versions(frozen, _raw_versions(_weights_path())) == []


def test_the_history_check_reports_an_edited_version() -> None:
    """Catches `_edited_versions` finding nothing wrong with a history that has been edited."""
    frozen = _raw_versions(FROZEN)
    history = copy.deepcopy(frozen)
    history[0]["rules"]["COMMUNICATED_WITH"]["heavy"] = 41
    assert _edited_versions(frozen, history) == [1]

    recalibrated = copy.deepcopy(frozen)
    recalibrated[0]["alpha"] = 0.6
    assert _edited_versions(frozen, recalibrated) == [1]

    gamma_changed = copy.deepcopy(frozen)
    gamma_changed[1]["gamma"] = 0.3
    assert _edited_versions(frozen, gamma_changed) == [2]

    appended = copy.deepcopy(frozen)
    later = copy.deepcopy(frozen[1])
    later["version"] = 3
    later["rules"]["COMMUNICATED_WITH"]["heavy"] = 41
    appended.append(later)
    assert _edited_versions(frozen, appended) == []

    assert _edited_versions(frozen, frozen[:1]) == [2]
    assert _edited_versions(frozen, []) == [1, 2]


# --- the loader ---------------------------------------------------------------


def _second_version() -> dict[str, Any]:
    version = copy.deepcopy(_raw_versions(FROZEN)[0])
    # Gamma 0, as ADR-123 requires of every version after 1: a second version with gamma 0.3 is
    # refused, so a "good" file must not carry one.
    version.update(version=2, alpha=0.6, gamma=0.0, midpoint=0.2 + 0.6 / 3, scale=0.6 / 3)
    return version


def _refused(path: Path) -> list[str]:
    """The message `OntologyError` carries from each loader for `path`; both must refuse it."""
    from ontology.errors import OntologyError
    from ontology.weights import load_weight_history, load_weight_rules

    messages: list[str] = []
    for load in (load_weight_rules, load_weight_history):
        with pytest.raises(OntologyError) as raised:
            load(path)
        messages.append(str(raised.value))
    return messages


def _names(message: str, version: int) -> bool:
    return re.search(rf"\bversion {version}\b", message) is not None


def test_version_two_loads_with_gamma_0_and_version_one_s_other_values() -> None:
    """ADR-123 decision 1. Catches a real weights file with no version 2, a version 2 whose gamma
    is not 0, one whose other parameters or rules are not version 1's, and a parameter set that
    does not name version 2. Read from the raw file and as the loader gives it."""
    from ontology.weights import load_weight_history, load_weight_rules

    raw_one, raw_two = _raw_versions(_weights_path())[:2]
    assert raw_two["version"] == 2
    assert raw_two["gamma"] == 0
    assert {k: v for k, v in raw_two.items() if k not in ("version", "gamma")} == {
        k: v for k, v in raw_one.items() if k not in ("version", "gamma")
    }

    one, two = load_weight_history()[:2]
    assert (one.version, one.gamma) == (1, 0.3)
    assert (two.version, two.gamma) == (2, 0.0)
    for field in ("alpha", "beta", "half_life_days", "midpoint", "scale", "default", "rules"):
        assert getattr(two, field) == getattr(one, field), field
    assert load_weight_rules().version >= 2
    assert two.parameter_set("COMMUNICATED_WITH") == "2/COMMUNICATED_WITH"
    assert two.parameter_set("FAMILY_OF") == "2/FAMILY_OF"
    assert two.parameter_set(UNLISTED) == "2/default"


def test_a_version_after_one_with_a_gamma_other_than_0_is_refused_naming_it(
    tmp_path: Path,
) -> None:
    """ADR-123 decision 2. Catches a loader that takes a version 2 or 3 carrying `gamma: 0.3`
    (mutual information over the whole corpus would be back), or refuses it without naming the
    version and the field. Positive controls differ only in gamma: version 1 may carry 0.3, and
    versions 2 and 3 carrying 0 load, so each refusal is for the gamma and nothing else."""
    from ontology.weights import load_weight_history

    frozen = _raw_versions(FROZEN)
    first, second = frozen[0], frozen[1]
    third = copy.deepcopy(second)
    third["version"] = 3

    assert first["gamma"] == 0.3
    only_one = _write_versions(tmp_path / "one.yaml", [first])
    assert [v.version for v in load_weight_history(only_one)] == [1]
    ok = _write_versions(tmp_path / "ok.yaml", [first, second, third])
    assert [(v.version, v.gamma) for v in load_weight_history(ok)] == [(1, 0.3), (2, 0.0), (3, 0.0)]

    second_gamma = copy.deepcopy(second)
    second_gamma["gamma"] = 0.3
    third_gamma = copy.deepcopy(third)
    third_gamma["gamma"] = 0.3
    #: label -> (the versions as written, the version the message must name)
    cases = {
        "version 2": ([first, second_gamma], 2),
        "version 3": ([first, second, third_gamma], 3),
    }
    for label, (versions, offending) in cases.items():
        path = _write_versions(tmp_path / f"{label.replace(' ', '_')}.yaml", versions)
        for message in _refused(path):
            assert _names(message, offending), (label, message)
            assert "gamma" in message, (label, message)
            assert "midpoint" not in message and "scale" not in message, (label, message)


def test_the_loader_refuses_versions_out_of_order(tmp_path: Path) -> None:
    """Catches a loader that takes a history that is not 1..n in order: a gap, a repeat, a file
    that starts at 2, or two versions the wrong way round, or one that refuses it without naming
    the offending version. A correct two-version file loads, so each refusal is for the order and
    not for the shape."""
    from ontology.weights import load_weight_history, load_weight_rules

    first = _raw_versions(FROZEN)[0]
    second = _second_version()

    good = _write_versions(tmp_path / "good.yaml", [first, second])
    assert [v.version for v in load_weight_history(good)] == [1, 2]
    latest = load_weight_rules(good)
    assert latest.version == 2
    assert latest.alpha == 0.6

    gap = copy.deepcopy(second)
    gap["version"] = 3
    starts_at_two = copy.deepcopy(first)
    starts_at_two["version"] = 2
    #: label -> (the versions as written, the offending version the message must name)
    cases = {
        "gap": ([first, gap], 3),
        "repeat": ([first, copy.deepcopy(first)], 1),
        "starts at two": ([starts_at_two], 2),
        "reversed": ([second, first], 2),
    }
    for label, (versions, offending) in cases.items():
        path = _write_versions(tmp_path / f"{label.replace(' ', '_')}.yaml", versions)
        for message in _refused(path):
            assert _names(message, offending), (label, message)


def test_the_loader_refuses_a_midpoint_that_is_not_derived(tmp_path: Path) -> None:
    """Catches a loader that takes a hand-tuned `midpoint` or `scale`, in the first version or a
    later one, or refuses it naming the wrong version, the wrong field or both fields."""
    from ontology.weights import load_weight_rules

    first = _raw_versions(FROZEN)[0]
    assert load_weight_rules(_write_versions(tmp_path / "ok.yaml", [first])).version == 1

    bad_midpoint = copy.deepcopy(first)
    bad_midpoint["midpoint"] = 0.4
    bad_scale = copy.deepcopy(first)
    bad_scale["scale"] = 0.2
    later = _second_version()
    later["midpoint"] = first["midpoint"]  # version 1's, not the one version 2's alpha gives
    #: label -> (versions, the field the message names, the field it must not, the version)
    cases = {
        "midpoint": ([bad_midpoint], "midpoint", "scale", 1),
        "scale": ([bad_scale], "scale", "midpoint", 1),
        "later version": ([first, later], "midpoint", "scale", 2),
    }
    for label, (versions, field, other, version) in cases.items():
        path = _write_versions(tmp_path / f"{label.replace(' ', '_')}.yaml", versions)
        for message in _refused(path):
            assert _names(message, version), (label, message)
            assert field in message, (label, message)
            assert other not in message, (label, message)
            if version == 2:
                assert not _names(message, 1), (label, message)


def test_the_loader_refuses_a_malformed_rule_naming_the_field(tmp_path: Path) -> None:
    """ADR-120 Amendment 4: a rule that sets both or neither of `heavy` and `fixed`, a `heavy`
    below 1 or a `fixed` outside (0, 1] is refused naming the version and the field; the bounds
    themselves (`heavy` 1, `fixed` 1) are accepted, so each refusal is for the value."""
    from ontology.weights import load_weight_rules

    first = _raw_versions(FROZEN)[0]

    def with_rule(name: str, rule: dict[str, Any]) -> list[dict[str, Any]]:
        version = copy.deepcopy(first)
        if name == "default":
            version["default"] = rule
        else:
            version["rules"][name] = rule
        return [version]

    for name, rule in (
        ("COMMUNICATED_WITH", {"unit": "one call", "heavy": 1}),
        ("FAMILY_OF", {"fixed": 1}),
        ("FAMILY_OF", {"fixed": 1.0}),
    ):
        ok = _write_versions(tmp_path / "ok.yaml", with_rule(name, rule))
        assert load_weight_rules(ok).version == 1

    #: (label, the rule's name, the rule as written, fields the message must name, and not name)
    cases = [
        (
            "both",
            "COMMUNICATED_WITH",
            {"unit": "one call", "heavy": 40, "fixed": 0.5},
            ("heavy", "fixed"),
            (),
        ),
        ("neither", "COMMUNICATED_WITH", {"unit": "one call"}, ("heavy", "fixed"), ()),
        ("heavy 0", "COMMUNICATED_WITH", {"unit": "one call", "heavy": 0}, ("heavy",), ("fixed",)),
        ("heavy -3", "VISITED", {"unit": "one visit", "heavy": -3}, ("heavy",), ("fixed",)),
        ("fixed 0", "FAMILY_OF", {"fixed": 0}, ("fixed",), ("heavy",)),
        ("fixed 1.5", "FAMILY_OF", {"fixed": 1.5}, ("fixed",), ("heavy",)),
        ("fixed -0.5", "DEPICTS", {"fixed": -0.5}, ("fixed",), ("heavy",)),
        (
            "default heavy 0",
            "default",
            {"unit": "one occurrence", "heavy": 0},
            ("heavy",),
            ("fixed",),
        ),
    ]
    for label, name, rule, named, not_named in cases:
        path = _write_versions(tmp_path / f"{label.replace(' ', '_')}.yaml", with_rule(name, rule))
        for message in _refused(path):
            assert _names(message, 1), (label, message)
            for field in named:
                assert field in message, (label, message)
            for field in not_named:
                assert field not in message, (label, message)


def _edited(tmp_path: Path, name: str, edit: Callable[[dict[str, Any]], None]) -> Path:
    """The frozen version 1, with `edit` applied to it, written as a weights file."""
    version = copy.deepcopy(_raw_versions(FROZEN)[0])
    edit(version)
    return _write_versions(tmp_path / f"{name.replace(' ', '_')}.yaml", [version])


def _with_derived(version: dict[str, Any], **changes: float) -> None:
    """Applies `changes` to the parameters and re-derives `midpoint` and `scale`, so a refusal is
    for the parameter and not for the derivation."""
    version.update(changes)
    version["scale"] = version["alpha"] / 3
    version["midpoint"] = version["beta"] + version["alpha"] / 3


def test_the_loader_refuses_every_malformed_parameter_naming_the_field(tmp_path: Path) -> None:
    """ADR-120 Amendment 4 decision 3. Catches a loader that takes a missing or non-numeric
    parameter, an alpha at or below 0 (it inverts the curve and breaks the same-pair invariant), a
    beta or gamma below 0, a half-life at or below 0, or a `version` that is not a whole number
    (`true` included), or that refuses one without naming the version and the field. The
    parameters are re-derived where they change, so each refusal is for the parameter."""
    from ontology.errors import OntologyError
    from ontology.weights import load_weight_history, load_weight_rules

    def drop(key: str) -> Callable[[dict[str, Any]], None]:
        return lambda v: v.pop(key)

    def put(key: str, value: object) -> Callable[[dict[str, Any]], None]:
        return lambda v: v.update({key: value})

    def derived(**changes: float) -> Callable[[dict[str, Any]], None]:
        return lambda v: _with_derived(v, **changes)

    #: label -> (the edit, the field the message must name)
    cases = {
        "missing alpha": (drop("alpha"), "alpha"),
        "missing beta": (drop("beta"), "beta"),
        "missing gamma": (drop("gamma"), "gamma"),
        "missing half-life": (drop("half_life_days"), "half_life_days"),
        "missing midpoint": (drop("midpoint"), "midpoint"),
        "missing scale": (drop("scale"), "scale"),
        "missing default": (drop("default"), "default"),
        "missing rules": (drop("rules"), "rules"),
        "text alpha": (put("alpha", "high"), "alpha"),
        "text gamma": (put("gamma", "some"), "gamma"),
        "boolean beta": (put("beta", True), "beta"),
        "alpha 0": (derived(alpha=0), "alpha"),
        "alpha -0.5": (derived(alpha=-0.5), "alpha"),
        "beta -0.1": (derived(beta=-0.1), "beta"),
        "gamma -0.3": (put("gamma", -0.3), "gamma"),
        "half-life 0": (put("half_life_days", 0), "half_life_days"),
        "half-life -90": (put("half_life_days", -90), "half_life_days"),
    }
    for label, (edit, field) in cases.items():
        path = _edited(tmp_path, label, edit)
        for message in _refused(path):
            assert _names(message, 1), (label, message)
            assert field in message, (label, message)
            if field not in ("midpoint", "scale"):
                assert "midpoint" not in message and "scale" not in message, (label, message)

    for label, bad in (("true", True), ("1.5", 1.5), ("text", "one")):
        path = _edited(tmp_path, f"version {label}", lambda v, bad=bad: v.update(version=bad))
        for load in (load_weight_rules, load_weight_history):
            with pytest.raises(OntologyError) as raised:
                load(path)
            assert "version" in str(raised.value), (label, str(raised.value))
            assert str(bad) in str(raised.value), (label, str(raised.value))


def test_the_loader_takes_a_whole_heavy_count_and_a_fixed_default(tmp_path: Path) -> None:
    """ADR-120 Amendment 4 decision 3. Catches a loader that refuses a YAML `12.0` as a heavy
    count (it is a whole number) or accepts a fractional one (2.5), and one that refuses a fixed
    default rule (the formula handles it): positive controls beside the refusals."""
    from ontology.weights import load_weight_rules

    whole = _edited(
        tmp_path,
        "whole",
        lambda v: v["rules"].update(SHARED_CELL_WITH={"unit": "one week", "heavy": 12.0}),
    )
    heavy = load_weight_rules(whole).rule_for("SHARED_CELL_WITH")[1].heavy
    assert heavy == 12 and isinstance(heavy, int)

    fractional = _edited(
        tmp_path,
        "fractional",
        lambda v: v["rules"].update(SHARED_CELL_WITH={"unit": "one week", "heavy": 2.5}),
    )
    for message in _refused(fractional):
        assert _names(message, 1) and "heavy" in message and "fixed" not in message, message

    fixed_default = _edited(tmp_path, "fixed default", lambda v: v.update(default={"fixed": 0.5}))
    rules = load_weight_rules(fixed_default)
    assert rules.rule_for("USES") == ("default", rules.default)
    assert rules.default.fixed == 0.5 and rules.default.heavy is None
    assert rules.parameter_set("USES") == "1/default"
    assert _weigh_under(rules, "USES") == 0.5


def _weigh_under(rules: Any, edge_type: str) -> float:
    from adapters.graph_arcadedb.weight import compute_weight

    return compute_weight(
        _independent(3),
        edge_type=edge_type,
        valid_to=None,
        now=NOW,
        rules=rules,
        self_loop=False,
    )


def test_the_loader_refuses_a_key_it_does_not_know_and_a_key_repeated(tmp_path: Path) -> None:
    """ADR-120 Amendment 4 decision 3. Catches a loader that drops a misspelt key without a word
    (`heavey` beside `fixed` would leave a rule that silently follows the formula), or that keeps
    the last of a key written twice (a second `alpha` overriding the first): each is refused
    naming the version and the key."""
    #: label -> (the edit, the key the message must name)
    unknown = {
        "heavey beside fixed": (
            lambda v: v["rules"].update(FAMILY_OF={"fixed": 0.75, "heavey": 3}),
            "heavey",
        ),
        "unit misspelt": (
            lambda v: v["rules"].update(VISITED={"unti": "one visit", "heavy": 8}),
            "unti",
        ),
        "gama": (lambda v: v.update(gama=0.3), "gama"),
        "unknown in default": (lambda v: v["default"].update(fixd=0.5), "fixd"),
    }
    for label, (edit, key) in unknown.items():
        for message in _refused(_edited(tmp_path, label, edit)):
            assert _names(message, 1) and key in message, (label, message)

    frozen = FROZEN.read_text(encoding="utf-8")
    #: label -> (the text with a key written twice, the key the message must name)
    repeated = {
        "alpha": (frozen.replace("    alpha: 0.5\n", "    alpha: 0.5\n    alpha: 0.9\n"), "alpha"),
        "rule": (
            frozen.replace(
                "      VISITED: {unit: one visit, heavy: 8}\n",
                "      VISITED: {unit: one visit, heavy: 8}\n"
                "      VISITED: {unit: one visit, heavy: 9}\n",
            ),
            "VISITED",
        ),
        "heavy within a rule": (
            frozen.replace("{unit: one call, heavy: 40}", "{unit: one call, heavy: 40, heavy: 41}"),
            "heavy",
        ),
    }
    for label, (text, key) in repeated.items():
        assert text != frozen, label
        path = tmp_path / f"repeat_{label.replace(' ', '_')}.yaml"
        path.write_text(text, encoding="utf-8")
        for message in _refused(path):
            assert _names(message, 1) and key in message, (label, message)
            assert "repeated" in message, (label, message)


def test_the_loader_refuses_a_value_that_is_not_finite(tmp_path: Path) -> None:
    """Catches a loader that takes `.nan` or `.inf` as a parameter: NaN passes every comparison the
    range checks make, and an infinite alpha with an infinite midpoint and scale is "derived".
    Each is refused naming the version and its own field (not `midpoint`)."""
    #: label -> (the edit, the field the message must name)
    cases = {
        "nan gamma": (lambda v: v.update(gamma=float("nan")), "gamma"),
        "nan beta": (lambda v: v.update(beta=float("nan")), "beta"),
        "inf half-life": (lambda v: v.update(half_life_days=float("inf")), "half_life_days"),
        "inf alpha": (
            lambda v: v.update(alpha=float("inf"), midpoint=float("inf"), scale=float("inf")),
            "alpha",
        ),
        "negative inf gamma": (lambda v: v.update(gamma=float("-inf")), "gamma"),
    }
    for label, (edit, field) in cases.items():
        for message in _refused(_edited(tmp_path, label, edit)):
            assert _names(message, 1) and field in message, (label, message)
            if field != "midpoint":
                assert "midpoint" not in message, (label, message)


def test_the_loader_refuses_yaml_it_cannot_construct(tmp_path: Path) -> None:
    """Catches a raw YAML error escaping the loader: text that composes but cannot be built (a
    `!!python/object` tag, which `safe_load` will not construct, and a mapping key that is itself
    a list) must be an `OntologyError`, as every other malformed file is."""
    frozen = FROZEN.read_text(encoding="utf-8")
    cases = {
        "python tag": frozen.replace(
            "    alpha: 0.5\n", "    alpha: !!python/object:os.system {}\n"
        ),
        "complex key": frozen.replace("    alpha: 0.5\n", "    alpha: 0.5\n    ? [a]\n    : 1\n"),
    }
    for label, text in cases.items():
        assert text != frozen, label
        path = tmp_path / f"{label.replace(' ', '_')}.yaml"
        path.write_text(text, encoding="utf-8")
        for message in _refused(path):
            assert "weights file" in message, (label, message)


# --- the invariant ------------------------------------------------------------

#: Each end's other occurrences, and the rest of the corpus beyond them.
OTHERS = (0, 1, 5, 50, 1000)
EXTRAS = (0, 1, 57, 100_000, 10_000_000)
STEPS = 120


@functools.cache
def _series() -> tuple[tuple[str, tuple[WeightComponents, ...]], ...]:
    """Series of the same pair at 1..STEPS occurrences with the rest of the corpus fixed: each
    end's degree is the pair's occurrences plus its own others, the total the pair's plus every
    other. `extra = 0` with no others at either end is the exclusive pair, p(u,v) = 1. A self-loop
    counts its occurrences twice in the degree of its one node."""
    out: list[tuple[str, tuple[WeightComponents, ...]]] = []
    for other_source, other_target, extra in itertools.product(OTHERS, OTHERS, EXTRAS):
        rest = other_source + other_target + extra
        out.append(
            (
                f"pair others=({other_source}, {other_target}) extra={extra}",
                tuple(
                    _components(
                        n,
                        source_degree=n + other_source,
                        target_degree=n + other_target,
                        total=n + rest,
                    )
                    for n in range(1, STEPS + 1)
                ),
            )
        )
    for other, extra in itertools.product(OTHERS, EXTRAS):
        out.append(
            (
                f"self-loop others={other} extra={extra}",
                tuple(
                    _components(
                        n,
                        source_degree=2 * n + other,
                        target_degree=2 * n + other,
                        total=n + other + extra,
                    )
                    for n in range(1, STEPS + 1)
                ),
            )
        )
    return tuple(out)


def _weigh_at(
    rules: Any, edge_type: str, valid_to: datetime | None, c: WeightComponents, self_loop: bool
) -> float:
    return _weigh(c, edge_type, valid_to=valid_to, self_loop=self_loop, rules=rules)


def _decreasing_steps(
    weigh: Callable[[WeightComponents, bool], float],
    *,
    only_self_loops: bool = False,
) -> list[str]:
    found: list[str] = []
    for label, series in _series():
        self_loop = label.startswith("self-loop")
        if only_self_loops and not self_loop:
            continue
        weights = [weigh(c, self_loop) for c in series]
        for n, (before, after) in enumerate(itertools.pairwise(weights), start=1):
            if after < before - 1e-12:
                found.append(f"{label}: {n} -> {n + 1} occurrences, {before} -> {after}")
    return found


@VERSIONS
def test_adding_occurrences_to_one_pair_never_lowers_its_weight(weights_version: int) -> None:
    """Catches any decrease in weight as one pair gains occurrences, for every counted rule and
    the default, at a recency held fixed; the grid includes the exclusive pair (p(u,v) = 1) and a
    self-loop (computed with self_loop=True, its mutual-information term 0)."""
    series = _series()
    assert any(label.endswith("extra=0") and "others=(0, 0)" in label for label, _ in series)
    assert any(label.startswith("self-loop") for label, _ in series)
    valid_to = NOW - timedelta(days=45)
    for edge_type in (*COUNTED, UNLISTED):
        found = _decreasing_steps(
            functools.partial(_weigh_at, _rules(weights_version), edge_type, valid_to)
        )
        assert found == [], f"{edge_type}: {found[:3]}"


def test_the_grid_would_catch_raw_pmi_under_the_count_term() -> None:
    """Rule 15: the grid above reports a decrease for the formula ADR-120 replaced, `log1p(n)`
    with raw PMI, so a green there is not a grid that cannot fail."""

    def old_weight(c: WeightComponents, self_loop: bool) -> float:
        p_pair = c.corpus_pair_count / c.corpus_total_occurrences
        p_source = c.corpus_source_degree / c.corpus_total_occurrences
        p_target = c.corpus_target_degree / c.corpus_total_occurrences
        raw = 0.5 * math.log1p(c.occurrences) + 0.2 + 0.3 * math.log(p_pair / (p_source * p_target))
        return raw

    found = _decreasing_steps(old_weight)
    assert found, "the grid found no decrease under raw PMI, so it proves nothing"
    assert any("others=(0, 0)" in line for line in found), found[:3]


def _count_dependent(rules: Any) -> list[str]:
    """Where a link's weight differs from the weight of the same link seen with no other link's
    count behind it: for every type, over the whole grid, each step's weight is compared with the
    weight of the same occurrences at the lone-link counts (`_components(n, n, n, n)`). The weight
    is taken as the store takes it for a pair, `self_loop=False`, so the mutual-information term
    is fully exposed to every count in the grid."""
    valid_to = NOW - timedelta(days=45)
    found: list[str] = []
    for edge_type in (*COUNTED, UNLISTED):
        alone = {
            n: _weigh(
                _components(n, source_degree=n, target_degree=n, total=n),
                edge_type,
                valid_to=valid_to,
                self_loop=False,
                rules=rules,
            )
            for n in range(1, STEPS + 1)
        }
        for label, series in _series():
            for n, components in enumerate(series, start=1):
                weight = _weigh(
                    components, edge_type, valid_to=valid_to, self_loop=False, rules=rules
                )
                if weight != alone[n]:
                    found.append(f"{edge_type} {label}: {n} occurrences, {alone[n]} -> {weight}")
    return found


def test_under_version_two_a_link_s_weight_is_the_same_whatever_its_corpus_counts() -> None:
    """ADR-123 decisions 1 and 3. Catches any corpus count (the pair's, either end's, the type's
    total) reaching a link's weight, which would let links a viewer cannot see move the weights of
    links they can. Over the whole grid, every type and the default. The same assertion is shown
    to fail under version 1 inside this test (rule 15): a green here is not a grid whose counts
    never mattered."""
    assert _count_dependent(_rules_v2()) == []
    under_one = _count_dependent(_rules(1))
    assert under_one, "no weight moved with its counts under version 1, so the grid proves nothing"
    # Version 1 moves with the type's total alone and with one end's degree alone, not only with
    # all of them at once.
    assert any("others=(0, 0) extra=57" in line for line in under_one), under_one[:3]
    assert any("others=(1000, 0) extra=0" in line for line in under_one), under_one[:3]


def test_the_grid_through_the_weight_would_catch_a_self_loop_not_told_it_is_one() -> None:
    """Rule 15, ADR-123 decision 3: Amendment 4's self-loop rule is still defined and its tests are
    pinned to version 1. Computed through `compute_weight` itself (the shape the store calls), a
    self-loop weighed with `self_loop=False` reports a decrease on the self-loop series under
    version 1; under version 2 it cannot, since the term is unused, which is why this case is
    pinned to version 1."""
    valid_to = NOW - timedelta(days=45)

    def told_it_is_not(rules: Any) -> list[str]:
        return _decreasing_steps(
            lambda c, _self_loop: _weigh(
                c, "COMMUNICATED_WITH", valid_to=valid_to, self_loop=False, rules=rules
            ),
            only_self_loops=True,
        )

    under_one = told_it_is_not(_rules(1))
    assert under_one, "no decrease with the flag missing under version 1: the series proves nothing"
    assert any("others=0 extra=57" in line for line in under_one), under_one[:3]
    assert told_it_is_not(_rules_v2()) == []
    # The flag, given, is what stops it under version 1 (the pinned case above).
    told = _decreasing_steps(
        lambda c, self_loop: _weigh(
            c, "COMMUNICATED_WITH", valid_to=valid_to, self_loop=self_loop, rules=_rules(1)
        ),
        only_self_loops=True,
    )
    assert told == []


def _by_hand(
    components: WeightComponents,
    *,
    heavy: int,
    recency: float,
    npmi_term: float,
) -> float:
    """`normalise(α·log1p(n)/log1p(heavy) + β·recency + γ·npmi)`, written out from §6.1."""
    midpoint, scale = 0.2 + 0.5 / 3, 0.5 / 3
    raw = (
        0.5 * math.log1p(components.occurrences) / math.log1p(heavy)
        + 0.2 * recency
        + 0.3 * npmi_term
    )
    return 1.0 / (1.0 + math.exp(-(raw - midpoint) / scale))


def test_a_self_loop_s_mutual_information_term_is_zero() -> None:
    """ADR-120 Amendment 4: catches a self-loop whose weight still takes the pair's mutual
    information (its degrees are counted twice, so the term misleads), and a structural
    self-loop that stops weighing its strength."""
    rules = _rules(1)  # pinned: the term is zero from version 2
    loop = _components(10, source_degree=20, target_degree=20, total=11)
    assert _npmi_by_hand(loop) == -1.0, "the case must be one where the term would matter"
    for valid_to, recency in ((None, 1.0), (NOW - timedelta(days=90), 0.5)):
        expected = _by_hand(loop, heavy=40, recency=recency, npmi_term=0.0)
        got = _weigh(loop, "COMMUNICATED_WITH", valid_to=valid_to, self_loop=True, rules=rules)
        assert got == pytest.approx(expected, abs=1e-9)
        pair = _weigh(loop, "COMMUNICATED_WITH", valid_to=valid_to, self_loop=False, rules=rules)
        assert pair < got - 1e-3, "the flag must change the weight where the term is not zero"
    default = _by_hand(loop, heavy=10, recency=1.0, npmi_term=0.0)
    assert _weigh(
        loop, UNLISTED, valid_to=None, self_loop=True, rules=rules
    ) == pytest.approx(default, abs=1e-9)
    for edge_type, strength in FIXED.items():
        assert _weigh(loop, edge_type, valid_to=None, self_loop=True, rules=rules) == strength


def _npmi_by_hand(c: WeightComponents) -> float:
    """`clamp(pmi / -ln p(u,v), -1, 1)`, from the formula in `01_DOMAIN_MODEL.md` §6.1, written
    out here and not taken from the implementation under test."""
    total = c.corpus_total_occurrences
    if total == 0 or c.corpus_pair_count == 0:
        return 0.0
    p_pair = c.corpus_pair_count / total
    p_source = c.corpus_source_degree / total
    p_target = c.corpus_target_degree / total
    if p_source == 0 or p_target == 0:
        return 0.0
    if p_pair == 1:
        return 1.0
    pmi = math.log(p_pair / (p_source * p_target))
    return max(-1.0, min(1.0, pmi / -math.log(p_pair)))


def test_the_grid_would_catch_a_self_loop_given_its_pmi() -> None:
    """Rule 15: the self-loop series, computed by hand with the npmi term NOT zeroed (the term is
    worked out in this test from the formula, not by the implementation), reports a decreasing
    step, so the green on the same series with the term zeroed is not a series that cannot
    fail."""
    valid_to_recency = 0.5 ** (45 / 90)

    def with_its_pmi(c: WeightComponents, self_loop: bool) -> float:
        return _by_hand(c, heavy=40, recency=valid_to_recency, npmi_term=_npmi_by_hand(c))

    found = _decreasing_steps(with_its_pmi, only_self_loops=True)
    assert found, "no decrease with the term left in, so the series proves nothing"
    assert all(line.startswith("self-loop") for line in found)
    assert any("others=0 extra=57" in line for line in found), found[:3]


# --- npmi ---------------------------------------------------------------------


def test_npmi_is_bounded_and_defined_at_every_edge_case() -> None:
    """Catches an undefined or out-of-range npmi, and one that is non-zero where the corpus gives
    nothing to compare against."""
    from adapters.graph_arcadedb.weight import npmi

    assert npmi(_components(0, source_degree=0, target_degree=0, total=0)) == 0.0
    assert npmi(_components(3, source_degree=3, target_degree=3, total=0)) == 0.0
    assert npmi(_components(0, source_degree=4, target_degree=4, total=9, pair=0)) == 0.0
    assert npmi(_components(1, source_degree=0, target_degree=5, total=9)) == 0.0
    assert npmi(_components(1, source_degree=5, target_degree=0, total=9)) == 0.0

    # p(u,v) = 1: the pair is the whole corpus; -ln p is zero, so the quotient is not taken.
    exclusive = _components(7, source_degree=7, target_degree=7, total=7)
    assert npmi(exclusive) == 1.0

    # A self-loop counts twice in a degree: p(u)·p(v) = (20/11)² > 1, so pmi / -ln p(u,v) falls
    # below -1 and is clamped.
    loop = _components(10, source_degree=20, target_degree=20, total=11)
    assert npmi(loop) == -1.0

    # An independent pair is exactly zero, and a pair that always occurs together is above it.
    assert npmi(_independent(5)) == pytest.approx(0.0, abs=1e-12)
    together = _components(5, source_degree=5, target_degree=5, total=500)
    assert 0.0 < npmi(together) <= 1.0

    for components in (c for _, series in _series()[::7] for c in series[::17]):
        value = npmi(components)
        assert math.isfinite(value)
        assert -1.0 <= value <= 1.0


# --- the calibration ----------------------------------------------------------


@VERSIONS
def test_a_counted_type_s_heavy_count_draws_at_the_logistic_of_two(weights_version: int) -> None:
    """Catches a count term that is not divided by the type's own heavy count: at its heavy
    count, recency 1 and npmi 0, every counted type draws at the logistic of 2 (about 0.8808)."""
    from adapters.graph_arcadedb.weight import npmi

    rules = _rules(weights_version)
    assert LOGISTIC_OF_TWO == pytest.approx(0.8808, abs=5e-5)
    for edge_type in COUNTED:
        _, rule = rules.rule_for(edge_type)
        assert rule.heavy is not None
        components = _independent(rule.heavy)
        assert npmi(components) == pytest.approx(0.0, abs=1e-12)
        assert _weigh(
            components, edge_type, valid_to=None, self_loop=False, rules=rules
        ) == pytest.approx(LOGISTIC_OF_TWO, abs=1e-9), edge_type
    default_heavy = rules.rule_for(UNLISTED)[1].heavy
    assert default_heavy == 10
    assert _weigh(
        _independent(10), UNLISTED, valid_to=None, self_loop=False, rules=rules
    ) == pytest.approx(LOGISTIC_OF_TWO, abs=1e-9)


@VERSIONS
def test_one_occurrence_draws_at_its_formula_value(weights_version: int) -> None:
    """Catches a one-occurrence figure the formula does not give for the type, for each of the
    seven counted rules and the default, at recency 1 and npmi 0; the figures the ADR quotes
    (about 0.392 for a type heavy at 40, 0.709 at 2 and 0.467 at the default) are checked too."""
    quoted = {"COMMUNICATED_WITH": 0.392, "IN_CONFLICT_WITH": 0.709, UNLISTED: 0.467}
    heavy_counts = {**{name: heavy for name, (_, heavy) in COUNTED.items()}, UNLISTED: 10}
    assert len(heavy_counts) == 8
    for edge_type, heavy in heavy_counts.items():
        count_term = math.log1p(1) / math.log1p(heavy)
        logit = (0.5 * count_term + 0.2 - (0.2 + 0.5 / 3)) / (0.5 / 3)
        expected = 1.0 / (1.0 + math.exp(-logit))
        got = _weigh(
            _independent(1),
            edge_type,
            valid_to=None,
            self_loop=False,
            rules=_rules(weights_version),
        )
        assert got == pytest.approx(expected, abs=1e-9), edge_type
        if edge_type in quoted:
            assert got == pytest.approx(quoted[edge_type], abs=5e-4), edge_type


def test_version_two_keeps_the_calibration_and_weighs_its_count_and_recency_alone() -> None:
    """ADR-123 decision 1: `midpoint` and `scale` are derived from alpha and beta alone, at a
    mutual-information term of 0, so version 2 draws a counted type's heavy count at the logistic
    of 2 and a one-off link at its formula value, whatever the counts behind it. Catches a version
    2 whose calibration drifted from version 1's."""
    rules = _rules_v2()
    for edge_type in COUNTED:
        heavy = rules.rule_for(edge_type)[1].heavy
        assert heavy is not None
        for components in (
            _independent(heavy),
            _components(heavy, source_degree=heavy, target_degree=heavy, total=heavy),
            _components(heavy, source_degree=heavy + 900, target_degree=heavy, total=10**7),
        ):
            assert _weigh(
                components, edge_type, valid_to=None, self_loop=False, rules=rules
            ) == pytest.approx(LOGISTIC_OF_TWO, abs=1e-9), edge_type
    quoted = {"COMMUNICATED_WITH": 0.392, "IN_CONFLICT_WITH": 0.709, UNLISTED: 0.467}
    for edge_type, figure in quoted.items():
        got = _weigh(_independent(1), edge_type, valid_to=None, self_loop=False, rules=rules)
        assert got == pytest.approx(figure, abs=5e-4), edge_type
    for edge_type, strength in FIXED.items():
        assert (
            _weigh(_independent(3), edge_type, valid_to=None, self_loop=False, rules=rules)
            == strength
        )


# --- structural types, default rule, parameter set ---------------------------


@VERSIONS
def test_a_structural_type_weighs_its_strength_whatever_its_occurrences(
    weights_version: int,
) -> None:
    """Catches a fixed rule that still follows its occurrences, recency or npmi."""
    rules = _rules(weights_version)
    for edge_type, strength in FIXED.items():
        for occurrences in (1, 5, 500):
            for valid_to in (None, NOW - timedelta(days=1), NOW - timedelta(days=1000)):
                for components in (
                    _independent(occurrences),
                    _components(
                        occurrences,
                        source_degree=occurrences,
                        target_degree=occurrences,
                        total=occurrences,
                    ),
                    _components(
                        occurrences,
                        source_degree=occurrences + 900,
                        target_degree=occurrences + 900,
                        total=occurrences + 10**6,
                    ),
                ):
                    assert (
                        _weigh(
                            components, edge_type, valid_to=valid_to, self_loop=False, rules=rules
                        )
                        == strength
                    ), (
                        edge_type,
                        occurrences,
                    )


@VERSIONS
def test_an_unlisted_type_takes_the_default_rule(weights_version: int) -> None:
    """Catches a type with no rule raising, or taking another type's heavy count."""
    rules = _rules(weights_version)
    name, rule = rules.rule_for(UNLISTED)
    assert (name, rule.heavy, rule.fixed) == ("default", 10, None)
    for components in (_independent(1), _independent(10), _independent(300)):
        assert _weigh(
            components, UNLISTED, valid_to=None, self_loop=False, rules=rules
        ) == _weigh(
            components, "SOME_TYPE_NO_FILE_NAMES", valid_to=None, self_loop=False, rules=rules
        )
    assert _weigh(
        _independent(10), UNLISTED, valid_to=None, self_loop=False, rules=rules
    ) != pytest.approx(
        _weigh(_independent(10), "COMMUNICATED_WITH", valid_to=None, self_loop=False, rules=rules),
        abs=1e-3,
    )


@VERSIONS
def test_the_parameter_set_names_the_version_and_the_rule(weights_version: int) -> None:
    """Catches a parameter set that does not name the version and the rule a weight was computed
    under, which is what makes a stored weight comparable with another."""
    rules = _rules(weights_version)
    assert rules.parameter_set("COMMUNICATED_WITH") == f"{rules.version}/COMMUNICATED_WITH"
    assert rules.parameter_set("FAMILY_OF") == f"{rules.version}/FAMILY_OF"
    assert rules.parameter_set(UNLISTED) == f"{rules.version}/default"
    from ontology.weights import load_weight_history

    one = load_weight_history()[0]
    assert one.parameter_set("COMMUNICATED_WITH") == "1/COMMUNICATED_WITH"
    assert one.parameter_set(UNLISTED) == "1/default"


# --- the principal's star -----------------------------------------------------


@VERSIONS
def test_on_a_star_the_heavy_links_outweigh_a_one_off_cell_share_and_the_picture(
    weights_version: int,
) -> None:
    """Catches a formula that draws the coordinator's calls and the shared payer's transfers no
    heavier than a one-off cell share or the picture. A synthetic star: the principal's 60 calls
    to the coordinator, the payer's 6 transfers to the principal, one week of cell sharing with
    one cellmate, the principal's picture, and four other links, each with realistic counts of
    other occurrences at both ends (values checked by arithmetic before this was built)."""
    #: name -> (type, occurrences, source degree, target degree, corpus total of the type)
    star = {
        "calls to the coordinator": ("COMMUNICATED_WITH", 60, 200, 150, 5000),
        "the payer's transfers": ("TRANSACTED", 6, 36, 26, 800),
        "one week of cell sharing": ("SHARED_CELL_WITH", 1, 21, 13, 400),
        "one report, first": ("MENTIONED_IN", 1, 9, 14, 500),
        "two reports": ("MENTIONED_IN", 2, 10, 12, 500),
        "three visits": ("VISITED", 3, 15, 40, 700),
        "family": ("FAMILY_OF", 1, 4, 4, 60),
        "membership": ("MEMBER_OF", 1, 3, 30, 90),
        "the picture": ("DEPICTS", 1, 2, 1, 40),
    }
    weights = {
        name: _weigh(
            _components(n, source_degree=ds, target_degree=dt, total=total),
            edge_type,
            valid_to=None,
            self_loop=False,
            rules=_rules(weights_version),
        )
        for name, (edge_type, n, ds, dt, total) in star.items()
    }
    ranked = sorted(weights, key=lambda name: weights[name], reverse=True)
    assert set(ranked[:2]) == {"calls to the coordinator", "the payer's transfers"}, weights
    assert set(ranked[-2:]) == {"one week of cell sharing", "the picture"}, weights
