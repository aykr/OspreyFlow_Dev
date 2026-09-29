"""Provider profiles — `spec/00_ARCHITECTURE.md` §1.2's "Provider
profiles" subsection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.provider_profile import (
    ProfileAuth,
    ProfileZoom,
    ProviderProfile,
)


def _profile(**overrides: object) -> ProviderProfile:
    base: dict[str, object] = {
        "id": "esri-arcgis-online",
        "label": "ESRI ArcGIS Online",
        "vendor": "ESRI",
        "kind": "raster",
        "service": "xyz",
        "endpoint": (
            "https://services.arcgisonline.com/ArcGIS/rest/services/"
            "{service}/MapServer/tile/{z}/{y}/{x}"
        ),
        "variables": {
            "service": {"default": "World_Imagery", "options": ["World_Imagery", "World_Topo_Map"]}
        },
        "auth": {"type": "none"},
        "projection": "EPSG:3857",
        "zoom": {"min": 0, "max": 19},
        "style": "bundled:osprey-raster-overlay",
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "licence": {
            "id": "esri-terms",
            "redistributable": False,
            "client_scope": "per-deployment",
            "note": "Subject to the deployment's own ESRI licence. Confirm before use.",
        },
        "proxy": "recommended",
    }
    base.update(overrides)
    return ProviderProfile.model_validate(base)


def test_the_architecture_docs_worked_example_round_trips() -> None:
    profile = _profile()
    assert profile.id == "esri-arcgis-online"
    assert profile.variables["service"].default == "World_Imagery"
    assert profile.licence.client_scope == "per-deployment"
    assert profile.zoom.min == 0 and profile.zoom.max == 19


def test_projection_must_be_an_epsg_reference() -> None:
    with pytest.raises(ValidationError, match="EPSG"):
        _profile(projection="3857")


def test_zoom_max_must_be_at_least_zoom_min() -> None:
    with pytest.raises(ValidationError, match="zoom.max"):
        ProfileZoom(min=10, max=5)


def test_auth_type_is_restricted_to_the_named_set() -> None:
    with pytest.raises(ValidationError):
        ProfileAuth(type="hmac")  # type: ignore[arg-type]
    assert ProfileAuth(type="oauth2").type == "oauth2"


def test_style_and_variables_are_optional() -> None:
    profile = _profile(style=None, variables={})
    assert profile.style is None
    assert profile.variables == {}
