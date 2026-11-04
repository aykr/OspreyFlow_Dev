"""The install answers file (`06_DECISIONS.md` ADR-114 Amendment 3 decision 5): what every question
writes and what `--config` reads, so the guided page, the prompts and CI install the same way — and
the `osprey.yaml` it becomes, validated by the deployment's own schema.

What a mistake would do, and the case that catches it:
- a typo in the file silently ignored — `test_an_unknown_key_is_refused_naming_it`;
- a mode or demo pack nobody built accepted — `test_an_unknown_mode_or_pack_is_refused`;
- the dashboards lost, as the hand-edited deployment showed they would be —
  `test_dashboards_are_on_by_default_and_reach_osprey_yaml`;
- the ingest or tiles folder left at a path that does not exist on a laptop —
  `test_the_folders_reach_storage_as_absolute_host_paths`;
- a generated `osprey.yaml` the renderer would refuse — every case validates it with `OspreyConfig`;
- the owner's own `osprey.yaml` rewritten when they asked for it to be used as it is —
  `test_a_named_config_is_used_as_it_is`;
- a cloud mode's answers dropped before B6/B7 can use them — `test_a_cloud_modes_answers_are_kept`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ospreyflow.answers import AnswersRefused, load_answers, osprey_config
from schemas.deployment import OspreyConfig


PACKS = ("hmp", "fixture-corp", "operation-ledger", "paysim")


def _base() -> dict[str, object]:
    """The product's committed defaults — what a fresh checkout's `osprey.yaml` holds."""
    import subprocess

    from tools.layout import ROOT

    text = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:OspreyFlow_Core/osprey.yaml"],
                          capture_output=True, text=True, check=True).stdout  # fmt: skip
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    return loaded


def _config(raw: dict[str, object], home: Path) -> OspreyConfig:
    answers = load_answers(raw, packs=PACKS, home=home)
    return OspreyConfig.model_validate(osprey_config(answers, _base()))


def test_the_smallest_file_is_a_valid_lite_install(tmp_path: Path) -> None:
    config = _config({"mode": "lite"}, tmp_path)
    assert config.profile.value == "local-lite"


def test_an_unknown_key_is_refused_naming_it(tmp_path: Path) -> None:
    with pytest.raises(AnswersRefused, match="dashbords"):
        load_answers({"mode": "lite", "components": {"dashbords": False}}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="colour"):
        load_answers({"mode": "lite", "colour": "blue"}, packs=PACKS, home=tmp_path)


def test_an_unknown_mode_or_pack_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AnswersRefused, match="medium"):
        load_answers({"mode": "medium"}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="enron"):
        load_answers({"mode": "lite", "demo_packs": ["hmp", "enron"]}, packs=PACKS, home=tmp_path)


def test_dashboards_are_on_by_default_and_reach_osprey_yaml(tmp_path: Path) -> None:
    on = _config({"mode": "lite"}, tmp_path)
    assert on.reporting.sync and on.reporting.superset
    off = _config({"mode": "lite", "components": {"dashboards": False}}, tmp_path)
    assert not off.reporting.sync and not off.reporting.superset


def test_the_folders_reach_storage_as_absolute_host_paths(tmp_path: Path) -> None:
    default = _config({"mode": "lite"}, tmp_path)
    assert default.components.storage.ingest == str(tmp_path / "OspreyFlow" / "ingest")
    assert default.components.storage.tiles == str(tmp_path / "OspreyFlow" / "basemap")
    chosen = _config({"mode": "lite", "folders": {"ingest": "~/evidence", "tiles": str(tmp_path / "maps")}},
                     tmp_path)  # fmt: skip
    assert chosen.components.storage.ingest == str(tmp_path / "evidence")
    assert chosen.components.storage.tiles == str(tmp_path / "maps")
    with pytest.raises(AnswersRefused, match="relative"):
        load_answers({"mode": "lite", "folders": {"ingest": "evidence"}}, packs=PACKS, home=tmp_path)


def test_models_stay_on_the_machine_unless_said_otherwise(tmp_path: Path) -> None:
    assert _config({"mode": "lite"}, tmp_path).models.local_only is True
    assert _config({"mode": "lite", "models": {"local_only": False}}, tmp_path).models.local_only is False


def test_the_demo_packs_and_paysims_file_are_kept(tmp_path: Path) -> None:
    answers = load_answers({"mode": "lite", "demo_packs": ["operation-ledger", "paysim"],
                            "paysim_file": "~/Downloads/paysim.csv"}, packs=PACKS, home=tmp_path)  # fmt: skip
    assert answers.demo_packs == ("operation-ledger", "paysim")
    assert answers.paysim_file == tmp_path / "Downloads" / "paysim.csv"
    with pytest.raises(AnswersRefused, match="paysim_file"):
        load_answers({"mode": "lite", "paysim_file": "/x.csv"}, packs=PACKS, home=tmp_path)


def test_a_named_config_is_used_as_it_is(tmp_path: Path) -> None:
    own = tmp_path / "osprey.yaml"
    own.write_text("profile: local-lite\nreporting:\n  sync: true\n  superset: false\n", encoding="utf-8")
    answers = load_answers({"mode": "lite", "config": str(own)}, packs=PACKS, home=tmp_path)
    assert osprey_config(answers, _base()) == yaml.safe_load(own.read_text(encoding="utf-8"))
    with pytest.raises(AnswersRefused, match="either"):
        load_answers({"mode": "lite", "config": str(own), "components": {"dashboards": False}},
                     packs=PACKS, home=tmp_path)  # fmt: skip


def test_a_cloud_modes_answers_are_kept(tmp_path: Path) -> None:
    answers = load_answers({"mode": "small", "cloud": {"provider": "azure", "region": "uksouth",
                            "domain": "osprey.example.org"}}, packs=PACKS, home=tmp_path)  # fmt: skip
    assert answers.cloud == {"provider": "azure", "region": "uksouth", "domain": "osprey.example.org"}
    with pytest.raises(AnswersRefused, match="gcp"):
        load_answers({"mode": "small", "cloud": {"provider": "gcp"}}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="cloud"):
        load_answers({"mode": "lite", "cloud": {"provider": "aws"}}, packs=PACKS, home=tmp_path)


def test_the_answers_set_the_address_every_name_derives_from(tmp_path: Path) -> None:
    """ADR-114 Amendment 4: whatever the committed `osprey.yaml` says, a Lite install answers at
    `http://ospreyflow.localhost` and a cloud install at its own domain over HTTPS."""
    assert _config({"mode": "lite"}, tmp_path).network.public_origin == "http://ospreyflow.localhost"
    small = load_answers({"mode": "small", "cloud": {"provider": "aws", "domain": "osprey.example.org"}},
                         packs=PACKS, home=tmp_path)  # fmt: skip
    assert osprey_config(small, _base())["network"]["public_origin"] == "https://osprey.example.org"


def test_the_answers_carry_a_mail_server_without_its_password(tmp_path: Path) -> None:
    """ADR-114 Amendment 5 (B4e): invitations by email when there is a mail server. Its password is
    never an answer: the install reads it from `OSPREY_SMTP_PASSWORD` and keeps it in the deployment's
    own secrets file."""
    raw = {"mode": "lite", "mail": {"host": "smtp.example.org", "port": 587, "from": "osprey@example.org",
                                    "starttls": True, "username": "osprey-mailer"}}  # fmt: skip
    assert _config(raw, tmp_path).mail is not None
    assert _config(raw, tmp_path).mail.from_address == "osprey@example.org"  # type: ignore[union-attr]
    with pytest.raises(AnswersRefused, match="password"):
        load_answers({**raw, "mail": {**raw["mail"], "password": "x"}}, packs=PACKS, home=tmp_path)  # type: ignore[dict-item]


def test_a_servers_managed_services_reach_osprey_yaml_and_validate(tmp_path: Path) -> None:
    """ADR-114 Amendment 10 point 1: the answers OpenTofu writes for the first boot name the managed
    services; they reach `osprey.yaml` as `external:`, which the deployment's schema checks."""
    external = {"postgres": {"host": "osprey-db.postgres.database.azure.com"},
                "media": {"blob_account": "ospreymedia1a2b"}}  # fmt: skip
    config = _config({"mode": "small", "external": external,
                      "cloud": {"provider": "azure", "domain": "osprey.example.org",
                                "dns_zone": "example.org", "admin_email": "ops@example.org"}},
                     tmp_path)  # fmt: skip
    assert config.external.postgres is not None
    assert config.external.postgres.host == "osprey-db.postgres.database.azure.com"
    assert config.external.media is not None and config.external.media.blob_account == "ospreymedia1a2b"
    with pytest.raises(AnswersRefused, match="external"):
        load_answers({"mode": "lite", "external": external}, packs=PACKS, home=tmp_path)


ENTERPRISE_EXTERNAL = {
    "postgres": {"host": "osprey.cluster-x.eu-west-2.rds.amazonaws.com"},
    "valkey": {"host": "osprey.x.cache.amazonaws.com"},
    "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
}


def test_an_enterprise_install_is_a_valid_cluster(tmp_path: Path) -> None:
    """ADR-114 Amendment 16: an Enterprise answers file makes an `osprey.yaml` a cluster renders —
    ClickHouse (a cluster's Conduits share it), and the cluster's namespace and storage classes."""
    config = _config({"mode": "enterprise", "external": ENTERPRISE_EXTERNAL,
                      "cloud": {"provider": "aws", "domain": "osprey.example.org"},
                      "cluster": {"namespace": "intel", "storage_class": "gp3",
                                  "shared_storage_class": "efs-sc"}},
                     tmp_path)  # fmt: skip
    assert config.profile.value == "cluster"
    assert config.components.analytics_engine.value == "clickhouse"
    assert (config.cluster.namespace, config.cluster.storage_class) == ("intel", "gp3")
    assert config.cluster.shared_storage_class == "efs-sc"
    assert config.network.public_origin == "https://osprey.example.org"


def test_cluster_answers_are_for_an_enterprise_install(tmp_path: Path) -> None:
    for mode in ("lite", "small"):
        with pytest.raises(AnswersRefused, match="cluster settings are for the enterprise mode"):
            load_answers({"mode": mode, "cluster": {"namespace": "x"}}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="nodes"):
        load_answers({"mode": "enterprise", "cluster": {"nodes": 3}}, packs=PACKS, home=tmp_path)


def _cloud(mode: str, api_cidrs: object) -> dict[str, object]:
    return {"mode": mode, "cloud": {"provider": "aws", "region": "eu-west-2",
                                    "domain": "osprey.example.org", "api_cidrs": api_cidrs}}  # fmt: skip


def test_the_addresses_the_clusters_api_answers_are_kept_and_go_no_further(tmp_path: Path) -> None:
    """ADR-114 Amendment 19: `cloud.api_cidrs` is what OpenTofu opens the cluster's API to; it is an
    input to the build, not a setting of the deployment."""
    raw = _cloud("enterprise", ["203.0.113.0/24", "2001:db8::/48"])
    answers = load_answers(raw, packs=PACKS, home=tmp_path)
    assert answers.api_cidrs == ("203.0.113.0/24", "2001:db8::/48")
    assert "api_cidrs" not in answers.cloud
    assert "api_cidrs" not in yaml.safe_dump(osprey_config(answers, _base()))


def test_the_whole_internet_or_a_non_address_is_refused_as_an_api_address(tmp_path: Path) -> None:
    for wrong, said in (
        (["0.0.0.0/0"], "whole internet"),
        (["::/0"], "whole internet"),
        (["198.51.100.7/0"], "whole internet"),
        (["osprey.example.org"], "not an address"),
        ("203.0.113.0/24", "a list"),
        ([], "at least one"),
    ):
        with pytest.raises(AnswersRefused, match=said):
            load_answers(_cloud("enterprise", wrong), packs=PACKS, home=tmp_path)


def test_api_addresses_are_for_an_enterprise_install(tmp_path: Path) -> None:
    with pytest.raises(AnswersRefused, match="api_cidrs is for the enterprise mode"):
        load_answers(_cloud("small", ["203.0.113.0/24"]), packs=PACKS, home=tmp_path)


# ---- ADR-114 Amendment 33 (drop 1): Small on a server of your own, `server:` ---------------------

SERVER = {
    "address": "https://osprey.example.internal",
    "certificate": "/etc/ospreyflow/tls/osprey.crt",
    "key": "/etc/ospreyflow/tls/osprey.key",
    "ca": "/etc/ospreyflow/tls/org-root.pem",
    "ingest": "/srv/ospreyflow/ingest",
}


def test_server_and_cloud_together_are_refused_in_words(tmp_path: Path) -> None:
    """Decision 1: a server is built with `--cloud`, or one you have is installed onto with
    `server:`, never both."""
    raw = {"mode": "small", "server": SERVER,
           "cloud": {"provider": "aws", "region": "eu-west-2", "domain": "osprey.example.org"}}  # fmt: skip
    with pytest.raises(AnswersRefused) as refused:
        load_answers(raw, packs=PACKS, home=tmp_path)
    assert "--cloud" in str(refused.value) and "server:" in str(refused.value)
    assert "not both" in str(refused.value)


def test_server_with_external_is_refused_in_words(tmp_path: Path) -> None:
    raw = {"mode": "small", "server": SERVER,
           "external": {"postgres": {"host": "osprey-db.example.org"}}}  # fmt: skip
    with pytest.raises(AnswersRefused) as refused:
        load_answers(raw, packs=PACKS, home=tmp_path)
    words = str(refused.value)
    assert "self-contained" in words and "every store in a container" in words
    assert "leave out server:" in words


@pytest.mark.parametrize("mode", ["lite", "enterprise"])
def test_a_server_section_is_refused_for_lite_and_enterprise(tmp_path: Path, mode: str) -> None:
    with pytest.raises(AnswersRefused) as refused:
        load_answers({"mode": mode, "server": SERVER}, packs=PACKS, home=tmp_path)
    assert "server:" in str(refused.value) and "small" in str(refused.value)
    assert mode in str(refused.value)


def test_server_answers_make_a_small_osprey_yaml_with_its_address_and_certificate_paths(
    tmp_path: Path,
) -> None:
    config = _config({"mode": "small", "server": {**SERVER, "redirect_http": True},
                      "components": {"dashboards": False}}, tmp_path)  # fmt: skip
    assert config.profile.value == "small"
    assert config.network.public_origin == "https://osprey.example.internal"
    assert config.network.tls is not None
    assert config.network.tls.certificate == SERVER["certificate"]
    assert config.network.tls.key == SERVER["key"]
    assert config.network.tls.ca == SERVER["ca"]
    assert config.network.redirect_http is True
    assert config.components.storage.ingest == SERVER["ingest"]
    assert not config.external.any
    assert config.reporting.superset is False
    # Without a CA and without the redirect, neither is written.
    bare = {k: v for k, v in SERVER.items() if k != "ca"}
    plain = _config({"mode": "small", "server": bare}, tmp_path)
    assert plain.network.tls is not None and plain.network.tls.ca is None
    assert plain.network.redirect_http is False


@pytest.mark.parametrize(
    ("server", "words"),
    [
        ({"certificate": "/c.pem", "key": "/k.pem"}, "server.address"),
        ({"address": "http://osprey.example.internal"}, "https://"),
        ({"address": "https://osprey.example.internal/glass"}, "no path"),
        ({"address": "https://osprey.example.internal", "certificate": "/c.pem"}, "both"),
        ({"address": "https://osprey.example.internal", "certificate": "tls/c.pem",
          "key": "/k.pem"}, "relative"),  # fmt: skip
        ({"address": "https://osprey.example.internal", "listen_address": "not-an-ip"},
         "listen_address"),
        ({"address": "https://osprey.example.internal", "memory_gib": 8}, "at least 16"),
        ({"address": "https://osprey.example.internal", "memory_gib": "lots"}, "auto or a number"),
        ({"address": "https://osprey.example.internal", "backups": "srv/b"}, "relative"),
        ({"address": "https://osprey.example.internal", "colour": "red"}, "colour"),
    ],
)
def test_a_server_section_that_cannot_be_installed_is_refused_naming_the_setting(
    tmp_path: Path, server: dict[str, object], words: str
) -> None:
    with pytest.raises(AnswersRefused) as refused:
        load_answers({"mode": "small", "server": server}, packs=PACKS, home=tmp_path)
    assert words in str(refused.value)


def test_the_first_administrators_email_is_taken_on_a_server(tmp_path: Path) -> None:
    answers = load_answers({"mode": "small", "server": SERVER, "admin_email": "ops@example.internal"},
                           packs=PACKS, home=tmp_path)  # fmt: skip
    assert answers.admin_email == "ops@example.internal"
    with pytest.raises(AnswersRefused, match="admin_email"):
        load_answers({"mode": "lite", "admin_email": "ops@example.internal"}, packs=PACKS,
                     home=tmp_path)  # fmt: skip


# ---- ADR-114 Amendment 33 drop 2: sign_in (unit 7), memory (unit 5), backups (unit 6) -------------

ORGANISATION = {"alias": "org", "label": "Example Organisation account",
                "issuer": "https://login.example.internal/tenant/v2.0", "client_id": "0000-1111"}  # fmt: skip


def test_organisation_sign_in_answers_name_the_provider_in_osprey_yaml(tmp_path: Path) -> None:
    """Decision 4: the provider's alias, label, issuer and client id reach `governance`; the client
    secret is never an answer (it is `OSPREY_ORG_SIGN_IN_SECRET` at install)."""
    config = _config({"mode": "small", "server": SERVER,
                      "sign_in": {"organisation": ORGANISATION}}, tmp_path)  # fmt: skip
    assert config.governance.organisation_sign_in == "org"
    provider = config.governance.organisation_provider
    assert provider is not None
    assert (provider.label, provider.issuer, provider.client_id) == (
        ORGANISATION["label"], ORGANISATION["issuer"], ORGANISATION["client_id"])  # fmt: skip
    # Alias and label have defaults; issuer and client id do not.
    bare = {"issuer": ORGANISATION["issuer"], "client_id": ORGANISATION["client_id"]}
    plain = _config({"mode": "small", "server": SERVER, "sign_in": {"organisation": bare}},
                    tmp_path)  # fmt: skip
    assert plain.governance.organisation_sign_in == "org"
    assert plain.governance.organisation_provider is not None


@pytest.mark.parametrize(
    ("raw", "words"),
    [
        ({"mode": "small", "server": SERVER,
          "sign_in": {"organisation": {**ORGANISATION, "client_secret": "s3cr3t"}}},
         "OSPREY_ORG_SIGN_IN_SECRET"),
        ({"mode": "small", "server": SERVER,
          "sign_in": {"organisation": {k: v for k, v in ORGANISATION.items() if k != "issuer"}}},
         "sign_in.organisation.issuer"),
        ({"mode": "small", "server": SERVER,
          "sign_in": {"organisation": {**ORGANISATION, "issuer": "http://login.example.internal"}}},
         "https://"),
        ({"mode": "small", "server": SERVER, "sign_in": {"groups": True}}, "groups"),
        ({"mode": "lite", "sign_in": {"organisation": ORGANISATION}}, "server:"),
        ({"mode": "small", "external": {"postgres": {"host": "db.example.org"}},
          "sign_in": {"organisation": ORGANISATION}}, "server:"),
    ],
)  # fmt: skip
def test_organisation_sign_in_answers_are_refused_in_words(
    tmp_path: Path, raw: dict[str, object], words: str
) -> None:
    with pytest.raises(AnswersRefused) as refused:
        load_answers(raw, packs=PACKS, home=tmp_path)
    assert words in str(refused.value), str(refused.value)
    assert "s3cr3t" not in str(refused.value)


def test_server_memory_and_backups_reach_osprey_yaml(tmp_path: Path) -> None:
    """Decisions 5 and 6: `server.backups` is where `ospreyflow backup` writes; a number for
    `server.memory_gib` is written as `resources.memory_gib` (`auto` is measured by the install)."""
    config = _config({"mode": "small",
                      "server": {**SERVER, "memory_gib": 64, "backups": "/srv/ospreyflow/backups"}},
                     tmp_path)  # fmt: skip
    assert config.resources.memory_gib == 64
    assert config.components.storage.backups == "/srv/ospreyflow/backups"
    answers = load_answers({"mode": "small", "server": {**SERVER, "memory_gib": "auto"}},
                           packs=PACKS, home=tmp_path)  # fmt: skip
    assert answers.memory_gib == "auto"
    assert "resources" not in osprey_config(answers, {})


# ---- ADR-135 Amendment 1: the local engine on an NVIDIA GPU (unit 1) -----------------------------


def test_server_gpu_reaches_osprey_yaml_and_none_writes_nothing(tmp_path: Path) -> None:
    """`server.gpu: nvidia` is written as `resources.gpu`; left out, or `none`, the `osprey.yaml`
    is what it was, so a deployment without a GPU renders byte for byte as before."""
    config = _config({"mode": "small", "server": {**SERVER, "gpu": "nvidia"}}, tmp_path)
    assert config.resources.gpu == "nvidia"
    for server in (SERVER, {**SERVER, "gpu": "none"}):
        answers = load_answers({"mode": "small", "server": server}, packs=PACKS, home=tmp_path)
        assert "resources" not in osprey_config(answers, {})


def test_server_gpu_other_than_none_or_nvidia_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AnswersRefused) as refused:
        load_answers({"mode": "small", "server": {**SERVER, "gpu": "amd"}}, packs=PACKS,
                     home=tmp_path)  # fmt: skip
    assert "server.gpu is none or nvidia" in str(refused.value)


@pytest.mark.parametrize(
    "beside",
    [
        {"cloud": {"provider": "aws", "region": "eu-west-2", "domain": "osprey.example.org"}},
        {"external": {"postgres": {"host": "db.example.org"}}},
    ],
    ids=["cloud", "external"],
)
def test_server_gpu_is_refused_for_a_clouds_server(
    tmp_path: Path, beside: dict[str, object]
) -> None:
    """A cloud's server (Small built with `cloud:`, or its first boot onto `external:`) is sized
    without a GPU (ADR-114), so the answer is refused naming it, not by the general rule."""
    raw = {"mode": "small", "server": {**SERVER, "gpu": "nvidia"}, **beside}
    with pytest.raises(AnswersRefused) as refused:
        load_answers(raw, packs=PACKS, home=tmp_path)
    assert "server.gpu" in str(refused.value)
    assert "without a GPU" in str(refused.value)
