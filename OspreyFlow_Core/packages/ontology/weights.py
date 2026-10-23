"""The link-weight rules — `spec/01_DOMAIN_MODEL.md` §6.1, ADR-120 D3 and Amendment 4.

`weights/default.yaml` holds an append-only list of versions. Each carries the formula's
parameters (alpha, beta, gamma, the half-life), the one deployment-wide `midpoint` and `scale`
(derived from alpha and beta, never hand-tuned), a `default` rule and one rule per link type. A
rule is either counted (`heavy`: the count that is heavy for the type, which divides the count
term) or fixed (`fixed`: a structural type's strength).

The loader refuses a malformed file with an `OntologyError` that names the version and the field:
versions that are not 1, 2, ... in order (a `version` that is not a whole number, `true`
included); a missing or non-numeric parameter; an alpha at or below 0, or a beta or gamma below 0;
a `half_life_days` at or below 0; a `midpoint` or `scale` that is not the derived one; a rule that
sets both or neither of `heavy` and `fixed`, a `heavy` below 1 or not a whole number (a YAML
`12.0` is one), or a `fixed` outside (0, 1]; and a key it does not know or a key repeated within
a mapping. A fixed default rule is allowed. A rule naming a link type no ontology composes is not
refused: this file is read before and apart from the ontology, and such a type simply never
occurs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import OntologyError

_DEFAULT_PATH = Path(__file__).resolve().parent / "weights" / "default.yaml"
_DERIVATION_TOLERANCE = 1e-9
DEFAULT_RULE = "default"
_RULE_KEYS = {"unit", "heavy", "fixed"}
_VERSION_KEYS = {
    "version",
    "alpha",
    "beta",
    "gamma",
    "half_life_days",
    "midpoint",
    "scale",
    "default",
    "rules",
}


@dataclass(frozen=True)
class Rule:
    """Exactly one of `heavy` (a counted rule) and `fixed` (a structural one) is set."""

    heavy: int | None = None
    fixed: float | None = None


@dataclass(frozen=True)
class WeightRules:
    """One version of the weights file."""

    version: int
    alpha: float
    beta: float
    gamma: float
    half_life_days: float
    midpoint: float
    scale: float
    default: Rule
    rules: Mapping[str, Rule]

    def rule_for(self, edge_type: str) -> tuple[str, Rule]:
        """The rule name and rule for a link type: its own, or `default` when it has none."""
        rule = self.rules.get(edge_type)
        if rule is None:
            return DEFAULT_RULE, self.default
        return edge_type, rule

    def parameter_set(self, edge_type: str) -> str:
        """`"<version>/<rule name>"`, stored beside every weight's components."""
        return f"{self.version}/{self.rule_for(edge_type)[0]}"


def _refuse_unknown(version: int, where: str, raw: Mapping[str, Any], known: set[str]) -> None:
    unknown = sorted(str(key) for key in raw if key not in known)
    if unknown:
        raise OntologyError(
            f"version {version}: {where} has an unknown key {unknown[0]!r} "
            f"(known keys: {', '.join(sorted(known))})"
        )


def _parse_rule(version: int, name: str, raw: Any) -> Rule:
    where = f"rule {name!r}"
    if not isinstance(raw, dict):
        raise OntologyError(f"version {version}: {where} must be a mapping with `heavy` or `fixed`")
    _refuse_unknown(version, where, raw, _RULE_KEYS)
    heavy, fixed = raw.get("heavy"), raw.get("fixed")
    if (heavy is None) == (fixed is None):
        raise OntologyError(
            f"version {version}: {where} must set exactly one of `heavy` and `fixed`"
        )
    if heavy is not None:
        # A YAML `12.0` is a whole number; `2.5`, `true` and text are not.
        if isinstance(heavy, float) and heavy.is_integer():
            heavy = int(heavy)
        if not isinstance(heavy, int) or isinstance(heavy, bool) or heavy < 1:
            raise OntologyError(
                f"version {version}: {where}: `heavy` must be a whole number of at least 1"
            )
        return Rule(heavy=heavy)
    if not isinstance(fixed, int | float) or isinstance(fixed, bool) or not 0 < fixed <= 1:
        raise OntologyError(
            f"version {version}: {where}: `fixed` must be a number above 0 and at most 1"
        )
    return Rule(fixed=float(fixed))


def _number(version: int, raw: Mapping[str, Any], key: str) -> float:
    value = raw.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise OntologyError(f"version {version}: `{key}` must be a finite number")
    return float(value)


def _parse_version(raw: Any, expected: int) -> WeightRules:
    if not isinstance(raw, dict):
        raise OntologyError(f"entry {expected} of the weights file is not a mapping")
    number = raw.get("version")
    if not isinstance(number, int) or isinstance(number, bool):
        raise OntologyError(
            f"entry {expected} of the weights file has `version: {number!r}`, "
            "which is not a whole number"
        )
    version = number
    if version != expected:
        raise OntologyError(
            f"version {version} is out of order: the weights file's versions must run 1, 2, ... "
            f"in order, and version {expected} was expected here"
        )
    _refuse_unknown(version, "the version", raw, _VERSION_KEYS)
    alpha = _number(version, raw, "alpha")
    beta = _number(version, raw, "beta")
    gamma = _number(version, raw, "gamma")
    half_life = _number(version, raw, "half_life_days")
    midpoint = _number(version, raw, "midpoint")
    scale = _number(version, raw, "scale")
    # A non-positive alpha inverts the count term and would silently break the same-pair
    # invariant; a negative beta or gamma inverts recency or exclusivity.
    if alpha <= 0:
        raise OntologyError(f"version {version}: `alpha` must be above 0")
    if beta < 0:
        raise OntologyError(f"version {version}: `beta` must not be below 0")
    if gamma < 0:
        raise OntologyError(f"version {version}: `gamma` must not be below 0")
    if half_life <= 0:
        raise OntologyError(f"version {version}: `half_life_days` must be above 0")
    derived_midpoint = beta + alpha / 3
    derived_scale = alpha / 3
    if not math.isclose(midpoint, derived_midpoint, abs_tol=_DERIVATION_TOLERANCE):
        raise OntologyError(
            f"version {version}: midpoint is {midpoint}, not the {derived_midpoint} "
            "derived from alpha and beta"
        )
    if not math.isclose(scale, derived_scale, abs_tol=_DERIVATION_TOLERANCE):
        raise OntologyError(
            f"version {version}: scale is {scale}, not the {derived_scale} derived from alpha"
        )
    default = _parse_rule(version, DEFAULT_RULE, raw.get("default"))
    raw_rules = raw.get("rules")
    if not isinstance(raw_rules, dict):
        raise OntologyError(f"version {version}: `rules` must be a mapping of link types")
    rules = {str(name): _parse_rule(version, str(name), rule) for name, rule in raw_rules.items()}
    return WeightRules(
        version=version,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        half_life_days=half_life,
        midpoint=midpoint,
        scale=scale,
        default=default,
        rules=rules,
    )


def _refuse_repeated_keys(text: str, source: Path) -> None:
    """A key written twice in one mapping is refused: PyYAML keeps the last of them and says
    nothing, so a second `alpha` would override the first unseen. Walks the parsed node tree
    (which keeps both) and names the version the repeat is in."""

    def walk(node: yaml.Node, version: str) -> None:
        if isinstance(node, yaml.MappingNode):
            seen: set[Any] = set()
            for key_node, value_node in node.value:
                if not isinstance(key_node, yaml.ScalarNode):
                    walk(value_node, version)
                    continue
                key = key_node.value
                if key in seen:
                    raise OntologyError(f"{version}: the key {key!r} is repeated within a mapping")
                seen.add(key)
                walk(value_node, version)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                walk(item, version)

    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as error:
        raise OntologyError(f"the weights file {source} is not valid YAML: {error}") from error
    if not isinstance(root, yaml.MappingNode):
        return
    for key_node, value_node in root.value:
        if getattr(key_node, "value", None) == "versions" and isinstance(
            value_node, yaml.SequenceNode
        ):
            for position, entry in enumerate(value_node.value, start=1):
                label = f"entry {position}"
                if isinstance(entry, yaml.MappingNode):
                    for entry_key, entry_value in entry.value:
                        if getattr(entry_key, "value", None) == "version" and isinstance(
                            entry_value, yaml.ScalarNode
                        ):
                            label = f"version {entry_value.value}"
                walk(entry, label)
    seen_top: set[Any] = set()
    for key_node, _ in root.value:
        key = getattr(key_node, "value", None)
        if key in seen_top:
            raise OntologyError(f"the weights file repeats the key {key!r} (repeated)")
        seen_top.add(key)


def load_weight_history(path: Path | None = None) -> list[WeightRules]:
    """Every version in the weights file, oldest first. Refuses a malformed file by name."""
    source = Path(path) if path is not None else _DEFAULT_PATH
    text = source.read_text(encoding="utf-8")
    _refuse_repeated_keys(text, source)
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as error:
        # Text that composes but cannot be built: a `!!python/object` tag, a list as a key.
        raise OntologyError(f"the weights file {source} cannot be read: {error}") from error
    if isinstance(loaded, dict):
        unknown = sorted(str(key) for key in loaded if key != "versions")
        if unknown:
            raise OntologyError(f"the weights file {source} has an unknown key {unknown[0]!r}")
    versions = loaded.get("versions") if isinstance(loaded, dict) else None
    if not isinstance(versions, list) or not versions:
        raise OntologyError(f"the weights file {source} holds no `versions` list")
    return [_parse_version(raw, expected) for expected, raw in enumerate(versions, start=1)]


def load_weight_rules(path: Path | None = None) -> WeightRules:
    """The latest version of the weights file: the one every new weight is computed under."""
    return load_weight_history(path)[-1]
