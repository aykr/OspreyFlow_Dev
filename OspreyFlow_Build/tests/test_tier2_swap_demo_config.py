"""The tier-1 -> tier-2 swap demonstration fixture — this
checkpoint's exit demonstration. Proves the fixture itself is
well-formed and stays within the "open, redistributable" bar the committed
demo config also holds to (`test_demo_osprey_config_is_tier_1_only.py`),
even though this fixture deliberately isn't that file (see its own header
comment for why). The actual live swap — a real Conduit serving this
config, the Glass rendering the tier-2 default — is verified by hand in a
running dev server/browser, per the standing UI rule; this test only
proves the config is loadable and licensing-clean before that happens.
"""

from __future__ import annotations

from pathlib import Path

from services.api.mapconfig_loader import load_map_config

from tools.osprey_bundle import bundle_map_providers

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mapconfig" / "tier2_swap_demo.osprey.yaml"


def test_the_default_provider_is_tier_2_and_needs_no_credential() -> None:
    config = load_map_config(FIXTURE)
    default = next(p for p in config.providers if p.id == config.default)
    assert default.id == "os-open-zoomstack-local"
    assert default.credential is None
    assert default.proxy == "none"
    assert default.source is not None and default.source.startswith("file://")


def test_every_provider_stays_open_and_redistributable() -> None:
    config = load_map_config(FIXTURE)
    for provider in config.providers:
        assert provider.licence.client_scope == "open", provider.id
        assert provider.licence.redistributable is True, provider.id


def test_osprey_bundle_accepts_the_swap_config() -> None:
    config = load_map_config(FIXTURE)
    result = bundle_map_providers(config)
    assert set(result.bundled_provider_ids) == {"osm-local", "os-open-zoomstack-local"}
