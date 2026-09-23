"""Loads a `providers/<id>.yaml` profile file — mirrors `mapconfig_loader.
load_map_config`'s `yaml.safe_load` + `model_validate` shape exactly
(`schemas/provider_profile.py`'s own module docstring).

Resolving a `MapProvider.profile` reference into an effective provider (so
`GET /v1/map/providers` can serve it, proxied like any tier-3/4 entry) is
the tile proxy's own job
— this module only proves a profile file itself is well-formed, the same
narrower scope `load_map_config` had before the Conduit wired it up.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from schemas.provider_profile import ProviderProfile


def load_provider_profile(path: str | Path) -> ProviderProfile:
    raw = yaml.safe_load(Path(path).read_text())
    return ProviderProfile.model_validate(raw)
