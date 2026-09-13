"""Handling scheme loader and evaluator — `docs/01_DOMAIN_MODEL.md` §2.2.

The enforcement logic reads the booleans a scheme declares (`dissemination`,
`direct_action`, `consult_originator`), never the code letters, so swapping
`uk-le.yaml` for `us-criminal-intelligence.yaml` — or enabling both — is a
configuration change with nothing above this module to touch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError

from schemas.domain import Handling

from .errors import HandlingSchemeError

_SCHEME_DIR = Path(__file__).resolve().parent / "handling"

Dissemination = Literal["permitted", "conditional", "restricted"]


class HandlingCode(BaseModel):
    label: str
    dissemination: Dissemination


class ActionCode(BaseModel):
    label: str
    direct_action: bool
    originator_permission: bool = False


class SanitisationCode(BaseModel):
    label: str
    consult_originator: bool


class HandlingScheme(BaseModel):
    name: str
    classification: list[str]
    handling_codes: dict[str, HandlingCode]
    action_codes: dict[str, ActionCode]
    sanitisation_codes: dict[str, SanitisationCode]


class HandlingDecision(BaseModel):
    """What the export gate and every dissemination decision branch on —
    never the raw code letters."""

    dissemination: Dissemination
    direct_action_permitted: bool
    originator_permission_required: bool
    consult_originator: bool


def load_handling_scheme(path: str | Path) -> HandlingScheme:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise HandlingSchemeError(f"{path}: handling scheme must be a YAML mapping")
    try:
        return HandlingScheme.model_validate({"name": path.stem, **raw})
    except ValidationError as exc:
        raise HandlingSchemeError(f"{path}: {exc}") from exc


def load_uk_le_scheme() -> HandlingScheme:
    return load_handling_scheme(_SCHEME_DIR / "uk-le.yaml")


def load_us_criminal_intelligence_scheme() -> HandlingScheme:
    return load_handling_scheme(_SCHEME_DIR / "us-criminal-intelligence.yaml")


def evaluate_handling(handling: Handling, scheme: HandlingScheme) -> HandlingDecision:
    """Evaluate one node/edge's `Handling` block against the active scheme."""
    if handling.classification not in scheme.classification:
        raise HandlingSchemeError(
            f"classification {handling.classification!r} is not defined in scheme {scheme.name!r}"
        )
    handling_code = scheme.handling_codes.get(handling.handling_code)
    if handling_code is None:
        raise HandlingSchemeError(
            f"handling code {handling.handling_code!r} is not defined in scheme {scheme.name!r}"
        )

    direct_action_permitted = False
    originator_permission_required = False
    if handling.action_code is not None:
        action_code = scheme.action_codes.get(handling.action_code)
        if action_code is None:
            raise HandlingSchemeError(
                f"action code {handling.action_code!r} is not defined in scheme {scheme.name!r}"
            )
        direct_action_permitted = action_code.direct_action
        originator_permission_required = action_code.originator_permission

    consult_originator = False
    if handling.sanitisation_code is not None:
        sanitisation_code = scheme.sanitisation_codes.get(handling.sanitisation_code)
        if sanitisation_code is None:
            raise HandlingSchemeError(
                f"sanitisation code {handling.sanitisation_code!r} is not defined in "
                f"scheme {scheme.name!r}"
            )
        consult_originator = sanitisation_code.consult_originator

    return HandlingDecision(
        dissemination=handling_code.dissemination,
        direct_action_permitted=direct_action_permitted,
        originator_permission_required=originator_permission_required,
        consult_originator=consult_originator,
    )
