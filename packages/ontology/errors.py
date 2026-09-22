"""Errors raised by the ontology and handling-scheme loaders."""

from __future__ import annotations


class OntologyError(Exception):
    """The ontology YAML is malformed or violates a business rule the JSON
    Schema cannot express — the nine-channel constraint, an unknown
    `pole_class`, or an attempt to redefine a system edge type."""


class HandlingSchemeError(Exception):
    """The handling-scheme YAML is malformed or references an undefined
    code from a node/edge's `Handling` block."""


class YardstickError(Exception):
    """The probability-yardstick YAML (`01_DOMAIN_MODEL.md` §5) is malformed, or a probability
    band label used by a judgement is not declared in the loaded yardstick."""
