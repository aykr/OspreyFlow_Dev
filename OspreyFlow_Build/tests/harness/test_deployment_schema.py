"""`packages/schemas/deployment.py` — `osprey.yaml` as a schema.

`06_DECISIONS.md` ADR-049's Stage 2 §1. The load-bearing case here is the first one: the committed
root `osprey.yaml` has only a `map:` key, and a schema that quietly made any other section required
would break it and `tests/test_demo_osprey_config_is_tier_1_only.py` together.
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from schemas.deployment import (
    ComponentsConfig,
    OspreyConfig,
    Profile,
    SearchBackend,
)
from tools.layout import REPO as REPO_ROOT

COMMITTED_CONFIG = REPO_ROOT / "osprey.yaml"


def test_the_committed_osprey_yaml_still_validates() -> None:
    """The constraint the review imposed on this schema, as a test rather than a promise. This is
    the real file, not a copy of its shape — a copy would keep passing after someone edited the
    original."""
    raw = yaml.safe_load(COMMITTED_CONFIG.read_text(encoding="utf-8"))
    config = OspreyConfig.model_validate(raw)

    assert set(raw) == {"map"}, (
        "the committed osprey.yaml has grown a second top-level key; this test's own premise "
        "(that a map-only file must validate) needs rechecking, not the assertion below"
    )
    assert config.map is not None
    assert config.map.default == "osm-local"
    assert config.profile is Profile.LOCAL_LITE


def test_an_empty_config_validates_and_every_section_defaults() -> None:
    """Every top-level key optional, stated as behaviour. If a future field is added without a
    default this fails here rather than at the first deployment that omits it."""
    config = OspreyConfig.model_validate({})

    assert config.profile is Profile.LOCAL_LITE
    assert config.components.graph_store.value == "arcadedb"
    assert config.components.analytics_engine.value == "duckdb"
    assert config.components.search is SearchBackend.OPENSEARCH
    assert config.models.local_only is True
    assert config.models.hosted_fallback is None
    assert config.models.sendable_handling_codes == []
    assert config.governance.handling_scheme == "uk-law-enforcement"
    assert config.governance.real_data_exceptions == "config/real_data_exceptions.yaml"
    assert config.cluster.hosts == []
    assert config.map is None


def test_the_map_section_reuses_mapconfig_rather_than_redefining_it() -> None:
    """Two schemas for one section is how the section's two readers start disagreeing. Asserted by
    round-tripping a real provider through `OspreyConfig` and checking `MapConfig`'s own validator
    still fires."""
    good = {
        "map": {
            "default": "osm-local",
            "providers": [
                {
                    "id": "osm-local",
                    "label": "OpenStreetMap",
                    "kind": "vector",
                    "source": "file:///data/tiles/osm-local.pmtiles",
                    "attribution": "© OpenStreetMap contributors",
                    "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
                }
            ],
        }
    }
    assert OspreyConfig.model_validate(good).map is not None

    bad = {**good, "map": {**good["map"], "default": "not-a-declared-provider"}}
    with pytest.raises(ValidationError, match="is not a declared provider"):
        OspreyConfig.model_validate(bad)


def test_a_misspelled_top_level_key_is_rejected_rather_than_ignored() -> None:
    """`extra="forbid"`, as behaviour. Without it a `governence:` typo renders a deployment with
    default governance and no complaint, and the failure surfaces much later as a wrong handling
    scheme rather than as a typo."""
    with pytest.raises(ValidationError, match="governence"):
        OspreyConfig.model_validate({"governence": {"handling_scheme": "us-criminal-intel"}})


def test_a_hosted_fallback_cannot_hide_behind_local_only() -> None:
    """`05_DEPLOYMENT.md` §2.1: models "Defaults to none", and `04_VAULT_BACKEND.md` §4's egress
    exception is off by default. A config naming a hosted fallback while still claiming
    `local_only` is ambiguous about whether egress is on, so it is refused rather than resolved in
    one direction silently."""
    with pytest.raises(ValidationError, match="local_only is true but a hosted_fallback"):
        OspreyConfig.model_validate({"models": {"hosted_fallback": "some-provider"}})


def test_handling_codes_cannot_be_sendable_to_nothing() -> None:
    with pytest.raises(ValidationError, match="cannot be sendable to nothing"):
        OspreyConfig.model_validate(
            {"models": {"local_only": False, "sendable_handling_codes": ["OFFICIAL"]}}
        )


CLUSTER_SERVICES = {
    "postgres": {"host": "osprey.cluster-x.eu-west-2.rds.amazonaws.com"},
    "valkey": {"host": "osprey.x.cache.amazonaws.com", "tls": True},
    "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
}


def test_cluster_hosts_belong_to_the_cluster_profile_only() -> None:
    """Hosts declared at another profile would be silently ignored."""
    with pytest.raises(ValidationError, match="only meaningful at profile: cluster"):
        OspreyConfig.model_validate(
            {"profile": "local-lite", "cluster": {"hosts": [{"name": "a", "address": "10.0.0.1"}]}}
        )


@pytest.mark.parametrize("missing", ["postgres", "valkey", "object_store"])
def test_a_cluster_names_the_managed_services_it_runs_on(missing: str) -> None:
    """05 §3b: on Kubernetes the cloud runs PostgreSQL, Valkey and the object store; a cluster
    naming none of one would render workloads with nothing to reach (ADR-114 Amendment 10)."""
    services = {k: v for k, v in CLUSTER_SERVICES.items() if k != missing}
    with pytest.raises(ValidationError, match=missing):
        OspreyConfig.model_validate({"profile": "cluster", "external": services})


def test_a_cluster_on_its_managed_services_is_valid() -> None:
    ok = OspreyConfig.model_validate({"profile": "cluster", "external": CLUSTER_SERVICES})
    assert ok.profile is Profile.CLUSTER
    assert ok.external.valkey is not None and ok.external.valkey.tls is True
    azure = {**CLUSTER_SERVICES, "object_store": None,
             "media": {"blob_account": "ospreymedia1a2b"}}  # fmt: skip
    assert OspreyConfig.model_validate({"profile": "cluster", "external": azure}).external.media
    with_search = {**CLUSTER_SERVICES, "search": {"url": "https://search-osprey.eu-west-2.es.amazonaws.com"}}
    assert OspreyConfig.model_validate({"profile": "cluster", "external": with_search}).external.search


def test_managed_valkey_and_search_are_for_a_cluster() -> None:
    with pytest.raises(ValidationError, match="cluster"):
        OspreyConfig.model_validate(
            {"profile": "small", "external": {"valkey": {"host": "x"}}}
        )


def test_duplicate_cluster_host_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="host names must be unique"):
        OspreyConfig.model_validate(
            {
                "profile": "cluster",
                "cluster": {
                    "hosts": [
                        {"name": "a", "address": "10.0.0.1"},
                        {"name": "a", "address": "10.0.0.2"},
                    ]
                },
            }
        )


def test_the_reduced_variant_is_declarable() -> None:
    """`05_DEPLOYMENT.md` §3's reduced variant. Preflight *offers* it (Stage 2 §2); this schema only
    has to be able to express it, which is what lets Stage 2 §1 render it when asked."""
    components = ComponentsConfig.model_validate({"search": "postgres-fulltext"})
    assert components.search is SearchBackend.POSTGRES_FULLTEXT


def test_the_tiles_folder_has_a_default_and_an_unknown_storage_key_is_still_refused() -> None:
    """`storage.tiles` is the host folder mounted at `/data/tiles`; an existing `osprey.yaml`
    without it must keep validating, and the model must still refuse a misspelt sibling."""
    from schemas.deployment import StorageRoots

    assert StorageRoots().tiles == "/var/lib/osprey/tiles"
    try:
        StorageRoots.model_validate({"tile": "/x"})
    except Exception:  # noqa: BLE001 - the refusal is what is asserted
        return
    raise AssertionError("a misspelt storage key must be refused, not ignored")
