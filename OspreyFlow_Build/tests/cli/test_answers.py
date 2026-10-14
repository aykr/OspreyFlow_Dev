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
