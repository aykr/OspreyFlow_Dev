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
#: S11: Small and Enterprise are HTTPS (the owner's ruling of 2 November 2026).
HTTPS = {"public_origin": "https://osprey.example.org"}


def test_the_committed_osprey_yaml_still_validates() -> None:
    """The constraint the review imposed on this schema, as a test rather than a promise. This is
    the real file, not a copy of its shape — a copy would keep passing after someone edited the
    original."""
    raw = yaml.safe_load(COMMITTED_CONFIG.read_text(encoding="utf-8"))
    config = OspreyConfig.model_validate(raw)

    # It began as a map-only file; since 39a80d0 it is the described example of every option, so
    # the premise is now that the whole example validates and names only sections that exist.
    assert set(raw) <= set(OspreyConfig.model_fields), set(raw) - set(OspreyConfig.model_fields)
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
        OspreyConfig.model_validate({"profile": "cluster", "external": services, "cluster": SHARED})


def test_a_cluster_on_its_managed_services_is_valid() -> None:
    ok = OspreyConfig.model_validate(
        {"profile": "cluster", "external": CLUSTER_SERVICES, "cluster": SHARED, "network": HTTPS}
    )
    assert ok.profile is Profile.CLUSTER
    assert ok.external.valkey is not None and ok.external.valkey.tls is True
    azure = {**CLUSTER_SERVICES, "object_store": None,
             "media": {"blob_account": "ospreymedia1a2b"}}  # fmt: skip
    assert OspreyConfig.model_validate(
        {"profile": "cluster", "external": azure, "cluster": SHARED, "network": HTTPS}
    ).external.media
    with_search = {**CLUSTER_SERVICES, "search": {"url": "https://search-osprey.eu-west-2.es.amazonaws.com"}}
    assert OspreyConfig.model_validate(
        {"profile": "cluster", "external": with_search, "cluster": SHARED, "network": HTTPS}
    ).external.search


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


# --- A cluster's own settings (05 §3b, ADR-114 Amendment 16) ------------------------------------

SHARED = {"shared_storage_class": "efs-sc"}


def test_a_cluster_names_the_storage_class_its_pods_share() -> None:
    """The ingest folder, the recipes and the model weights are one volume every Conduit mounts
    (ReadWriteMany): EKS and AKS have no default class that can do that, so a cluster names one."""
    with pytest.raises(ValidationError, match="shared_storage_class"):
        OspreyConfig.model_validate({"profile": "cluster", "external": CLUSTER_SERVICES})
    ok = OspreyConfig.model_validate(
        {"profile": "cluster", "external": CLUSTER_SERVICES, "cluster": SHARED, "network": HTTPS}
    )
    assert ok.cluster.namespace == "ospreyflow"
    assert ok.cluster.shared_storage_class == "efs-sc" and ok.cluster.storage_class is None


@pytest.mark.parametrize("namespace", ["OspreyFlow", "osprey_flow", "-osprey", "x" * 64, ""])
def test_a_cluster_namespace_is_a_kubernetes_name(namespace: str) -> None:
    with pytest.raises(ValidationError, match="namespace"):
        OspreyConfig.model_validate(
            {"profile": "cluster", "external": CLUSTER_SERVICES,
             "cluster": {**SHARED, "namespace": namespace}}
        )  # fmt: skip


@pytest.mark.parametrize("setting", [{"namespace": "osprey"}, {"storage_class": "gp3"}, SHARED])
def test_a_clusters_settings_belong_to_the_cluster_profile_only(setting: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="only meaningful at profile: cluster"):
        OspreyConfig.model_validate({"profile": "small", "cluster": setting})


# --- S11 and O2: the address's scheme and domain against the profile (GDS re-audit; the owner's
# --- ruling of 2 November 2026; `05_DEPLOYMENT.md` §7) -------------------------------------------


def _profile(profile: str, origin: str | None) -> dict[str, object]:
    raw: dict[str, object] = {"profile": profile}
    if profile == "cluster":
        raw |= {"external": CLUSTER_SERVICES, "cluster": SHARED}
    if origin is not None:
        raw["network"] = {"public_origin": origin}
    return raw


@pytest.mark.parametrize("profile", ["small", "cluster"])
@pytest.mark.parametrize(
    "origin", ["http://osprey.example.org", "http://ospreyflow.localhost", "http://10.0.0.5:8080", None]
)
def test_small_and_enterprise_refuse_a_plain_http_address_in_words(
    profile: str, origin: str | None
) -> None:
    """S11: Small and Enterprise are reached by other people over a network, so their address is
    HTTPS, with the certificate the front proxy obtains. An edited `osprey.yaml` could serve either
    over plain HTTP; it is refused, saying why and what to write instead. No address at all is the
    Lite default, plain HTTP, and is refused the same way."""
    assert OspreyConfig.model_validate(_profile(profile, HTTPS["public_origin"])).profile.value == profile
    with pytest.raises(ValidationError) as refused:
        OspreyConfig.model_validate(_profile(profile, origin))
    words = str(refused.value)
    assert "must be an https:// address" in words, words
    assert ("a Small" if profile == "small" else "an Enterprise") in words, words


@pytest.mark.parametrize(
    "origin",
    ["https://intel.service.gov.uk", "http://intel.service.gov.uk", "https://Intel.Service.GOV.UK",
     "https://gov.uk", "http://osprey.gov.uk:8080"],
)  # fmt: skip
def test_a_gov_uk_address_refuses_lite_in_words(origin: str) -> None:
    """O2, as the owner ruled it: a gov.uk address is a public service, and Lite answers on this
    computer only in plain HTTP. Lite with a gov.uk address is refused, naming Small or Enterprise;
    the same address on Small validates."""
    with pytest.raises(ValidationError) as refused:
        OspreyConfig.model_validate({"network": {"public_origin": origin}})
    words = str(refused.value)
    assert "gov.uk address" in words and "Lite" in words and "Small or Enterprise" in words, words
    if origin.startswith("https://"):
        assert OspreyConfig.model_validate(_profile("small", origin)).profile is Profile.SMALL


@pytest.mark.parametrize(
    "origin",
    ["http://ospreyflow.localhost", "http://govuk.ospreyflow.localhost:8081", "http://alpha.localhost:8090",
     "http://localhost:8080", "https://osprey.localhost", "http://notgov.uk.example.org", "http://fakegov.uk"],
)  # fmt: skip
def test_lite_keeps_its_own_addresses(origin: str) -> None:
    """Both of the owner's deployments (Lite at a `*.localhost` address, one with the GOV.UK brand)
    and every address the install and the starters give Lite still validate; a name that merely
    contains "gov.uk" is not a gov.uk address."""
    assert OspreyConfig.model_validate({"network": {"public_origin": origin}}).profile is Profile.LOCAL_LITE
    govuk = {"brand": "govuk", "service_name": "Intelligence", "organisation": "Ministry of Examples"}
    assert OspreyConfig.model_validate({"network": {"public_origin": origin}, "appearance": govuk})


# ---- ADR-114 Amendment 33 (drop 1): the organisation's own certificate -------------------------

_TLS = {"certificate": "/etc/ospreyflow/tls/osprey.crt", "key": "/etc/ospreyflow/tls/osprey.key"}


def _small(**network: object) -> dict[str, object]:
    return {"profile": "small",
            "network": {"public_origin": "https://osprey.example.internal", **network}}  # fmt: skip


@pytest.mark.parametrize(
    ("profile", "origin"),
    [("local-lite", "http://ospreyflow.localhost"), ("cluster", "https://osprey.example.org")],
)
@pytest.mark.parametrize(
    "setting", [{"tls": _TLS}, {"redirect_http": True}, {"listen_address": "192.0.2.10"}]
)
def test_tls_paths_are_refused_on_lite_and_enterprise_in_words(
    profile: str, origin: str, setting: dict[str, object]
) -> None:
    raw: dict[str, object] = {"profile": profile, "network": {"public_origin": origin, **setting}}
    if profile == "cluster":
        raw["cluster"] = {"shared_storage_class": "efs-sc"}
        raw["external"] = {"postgres": {"host": "db.example.org"}, "valkey": {"host": "v.example.org"},
                           "object_store": {"endpoint": "s3.example.org", "region": "eu-west-2"}}  # fmt: skip
    with pytest.raises(ValidationError) as refused:
        OspreyConfig.model_validate(raw)
    words = str(refused.value)
    assert "Small on a server of your own" in words, words
    name = next(iter(setting))
    assert f"network.{name}" in words, words


def test_tls_paths_must_be_absolute() -> None:
    assert OspreyConfig.model_validate(_small(tls=_TLS)).network.tls is not None
    for relative in ({**_TLS, "certificate": "tls/osprey.crt"}, {**_TLS, "key": "~/osprey.key"},
                     {**_TLS, "ca": "org-root.pem"}):  # fmt: skip
        with pytest.raises(ValidationError, match="absolute path"):
            OspreyConfig.model_validate(_small(tls=relative))


def test_the_certificate_and_its_options_belong_to_a_self_contained_small() -> None:
    """Every new setting is refused outside a self-contained Small (Amendment 33's consequences):
    with managed services, with no certificate of its own (the redirect and the one interface
    have no meaning beside Caddy's own certificate, which needs port 80 for its challenge), and a
    listen address that is not an address."""
    external = {"postgres": {"host": "db.example.org"}}
    with pytest.raises(ValidationError, match="every store in a container"):
        OspreyConfig.model_validate({**_small(tls=_TLS), "external": external})
    for setting in ({"redirect_http": True}, {"listen_address": "192.0.2.10"}):
        with pytest.raises(ValidationError, match="network.tls"):
            OspreyConfig.model_validate(_small(**setting))
    with pytest.raises(ValidationError, match="listen_address"):
        OspreyConfig.model_validate(_small(tls=_TLS, listen_address="osprey.example.internal"))
    chosen = OspreyConfig.model_validate(
        _small(tls={**_TLS, "ca": "/etc/ospreyflow/tls/org-root.pem"}, redirect_http=True,
               listen_address="192.0.2.10")
    )  # fmt: skip
    assert chosen.network.redirect_http and chosen.network.listen_address == "192.0.2.10"


# ---- ADR-114 Amendment 33 decision 4 (drop 2, unit 7): the organisation's identity provider -------

_PROVIDER = {"label": "Example Organisation account",
             "issuer": "https://login.example.internal/realms/org", "client_id": "osprey"}  # fmt: skip


def _small_with_provider(**governance: object) -> dict[str, object]:
    return {**_small(tls=_TLS), "governance": {"organisation_sign_in": "org",
                                                "organisation_provider": _PROVIDER, **governance}}  # fmt: skip


def test_the_organisations_provider_is_named_on_a_small_with_its_alias() -> None:
    config = OspreyConfig.model_validate(_small_with_provider())
    provider = config.governance.organisation_provider
    assert provider is not None
    assert (provider.label, provider.issuer, provider.client_id) == (
        _PROVIDER["label"], _PROVIDER["issuer"], _PROVIDER["client_id"])  # fmt: skip
    # It holds no secret: the model has no field for one, and refuses one by name.
    with pytest.raises(ValidationError, match="client_secret"):
        OspreyConfig.model_validate(
            _small_with_provider(organisation_provider={**_PROVIDER, "client_secret": "x"})
        )


@pytest.mark.parametrize(
    ("profile", "origin"),
    [("local-lite", "http://ospreyflow.localhost"), ("cluster", "https://osprey.example.org")],
)
def test_the_organisations_provider_is_refused_on_lite_and_enterprise_in_words(
    profile: str, origin: str
) -> None:
    raw: dict[str, object] = {
        "profile": profile, "network": {"public_origin": origin},
        "governance": {"organisation_sign_in": "org", "organisation_provider": _PROVIDER},
    }  # fmt: skip
    if profile == "cluster":
        raw["cluster"] = {"shared_storage_class": "efs-sc"}
        raw["external"] = {"postgres": {"host": "db.example.org"}, "valkey": {"host": "v.example.org"},
                           "object_store": {"endpoint": "s3.example.org", "region": "eu-west-2"}}  # fmt: skip
    with pytest.raises(ValidationError) as refused:
        OspreyConfig.model_validate(raw)
    words = str(refused.value)
    assert "governance.organisation_provider" in words and "profile: small" in words, words


@pytest.mark.parametrize(
    ("governance", "words"),
    [
        ({"organisation_sign_in": None}, "governance.organisation_sign_in"),
        ({"organisation_sign_in": "org/../x"}, "letters, digits"),
        ({"organisation_provider": {**_PROVIDER, "issuer": "http://login.example.internal"}},
         "https://"),
        ({"organisation_provider": {**_PROVIDER, "issuer": "https://login.example.internal/"}},
         "end with '/'"),
        ({"organisation_provider": {**_PROVIDER, "client_id": ""}}, "client_id"),
    ],
)
def test_the_organisations_provider_is_refused_without_what_keycloak_needs(
    governance: dict[str, object], words: str
) -> None:
    """The alias is part of the redirect URI the organisation registers, so it is refused unless it
    is plain; the issuer is the provider's own address, read over HTTPS for its discovery
    document."""
    with pytest.raises(ValidationError) as refused:
        OspreyConfig.model_validate(_small_with_provider(**governance))
    assert words in str(refused.value), str(refused.value)
