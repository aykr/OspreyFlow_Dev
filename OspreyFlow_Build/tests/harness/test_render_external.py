"""Small on a cloud's managed services (`05_DEPLOYMENT.md` §3a, ADR-114 Amendment 10): what
`external:` names is not rendered as a container, everything that used it reaches the managed
service instead, over TLS, through the `egress` network — and nothing names a secret.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.apply import ApplyRefused, managed_service_lines
from harness.render import load_config, render
from pydantic import ValidationError
from schemas.deployment import OspreyConfig
from tools.layout import CORE

from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver

RDS = "osprey-db.abc.eu-west-2.rds.amazonaws.com"
AWS = {
    "postgres": {"host": RDS, "user": "osprey", "database": "ospreyflow"},
    "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2",
                     "bucket_prefix": "osprey-small-1a2b-"},
}  # fmt: skip
AZURE = {
    "postgres": {"host": "osprey-db.postgres.database.azure.com"},
    "media": {"blob_account": "ospreymedia1a2b", "blob_container": "media"},
}


def _config(tmp_path: Path, external: dict[str, Any], profile: str = "small") -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return OspreyConfig.model_validate(
        {
            **loaded.model_dump(mode="json"),
            "profile": profile,
            "external": external,
            "components": {**loaded.components.model_dump(mode="json"), "source_path": str(CORE)},
        }
    )


def _services(config: OspreyConfig) -> dict[str, Any]:
    rendered = render(config, resolver=_fake_resolver).artefacts["compose.yaml"]
    return yaml.safe_load(rendered)["services"]  # type: ignore[no-any-return]


def test_lite_cannot_name_external_services(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="small and cluster profiles"):
        _config(tmp_path, AWS, profile="local-lite")


def test_on_aws_neither_postgres_nor_the_object_store_is_a_container(tmp_path: Path) -> None:
    services = _services(_config(tmp_path, AWS))
    assert "postgres" not in services and "objectstore" not in services
    for name, service in services.items():
        assert "postgres" not in (service.get("depends_on") or {}), name
        assert "objectstore" not in (service.get("depends_on") or {}), name


def test_on_azure_postgres_is_managed_and_seaweedfs_stays(tmp_path: Path) -> None:
    services = _services(_config(tmp_path, AZURE))
    assert "postgres" not in services
    assert services["objectstore"]["image"] == "chrislusf/seaweedfs:4.48"


def test_keycloak_and_its_database_step_reach_the_managed_server_over_tls(tmp_path: Path) -> None:
    services = _services(_config(tmp_path, AWS))
    keycloak = services["keycloak"]
    assert keycloak["environment"]["KC_DB_URL"] == (
        f"jdbc:postgresql://{RDS}:5432/keycloak?sslmode=require"
    )
    assert "postgres" not in keycloak["depends_on"]
    step = services["keycloak-db"]
    script = step["command"][0]
    assert f"-h {RDS} -p 5432" in script and "-h postgres" not in script
    assert step["environment"]["PGSSLMODE"] == "require"
    assert "depends_on" not in step or "postgres" not in step["depends_on"]


def test_what_reaches_a_managed_service_has_a_route_out_and_nothing_else_does(
    tmp_path: Path,
) -> None:
    services = _services(_config(tmp_path, AWS))
    reaching = {name for name, s in services.items() if "egress" in s["networks"]}
    for name in ("api", "ingest", "keycloak", "keycloak-db"):
        assert name in reaching, name
    for name in ("arcadedb", "valkey", "workspace", "ner", "ollama"):
        assert name not in reaching, name


def test_lite_is_rendered_as_before(tmp_path: Path) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    config = loaded.model_copy(
        update={"components": loaded.components.model_copy(update={"source_path": str(CORE)})}
    )
    services = _services(config)
    assert {"postgres", "objectstore", "keycloak-db"} <= set(services)
    assert services["keycloak"]["environment"]["KC_DB_URL"] == (
        "jdbc:postgresql://postgres:5432/keycloak"
    )
    assert "-h postgres" in services["keycloak-db"]["command"][0]


# --- the deployment.env lines apply writes ---------------------------------------------------


def _lines(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def test_aws_lines_point_at_rds_and_s3_with_no_key(tmp_path: Path) -> None:
    env = {"OSPREY_POSTGRES_PASSWORD": "from-secrets-manager"}
    lines = _lines(managed_service_lines(_config(tmp_path, AWS), environ=env, minted="m",
                                         object_store_password="o"))  # fmt: skip
    assert (lines["POSTGRES_HOST"], lines["POSTGRES_PORT"]) == (RDS, "5432")
    assert lines["POSTGRES_SSLMODE"] == "require"
    assert lines["POSTGRES_PASSWORD"] == lines["OSPREY_POSTGRES_PASSWORD"] == "from-secrets-manager"
    assert lines["MINIO_ENDPOINT"] == "s3.eu-west-2.amazonaws.com"
    assert (lines["MINIO_USE_SSL"], lines["MINIO_REGION"]) == ("true", "eu-west-2")
    assert lines["MINIO_CREDENTIALS"] == "instance"
    assert lines["MINIO_BUCKET_PREFIX"] == "osprey-small-1a2b-"
    assert "MINIO_ACCESS_KEY" not in lines and "MINIO_SECRET_KEY" not in lines


def test_azure_lines_put_media_on_blob_and_keep_seaweedfs(tmp_path: Path) -> None:
    env = {"OSPREY_POSTGRES_PASSWORD": "kv", "AZURE_STORAGE_KEY": "a2V5"}
    lines = _lines(managed_service_lines(_config(tmp_path, AZURE), environ=env, minted="m",
                                         object_store_password="o"))  # fmt: skip
    assert lines["OSPREY_MEDIA_STORE"] == "blob"
    assert (lines["AZURE_STORAGE_ACCOUNT"], lines["AZURE_MEDIA_CONTAINER"]) == (
        "ospreymedia1a2b", "media",
    )  # fmt: skip
    assert lines["AZURE_STORAGE_KEY"] == "a2V5"
    assert lines["MINIO_ENDPOINT"] == "objectstore:8333"
    assert lines["MINIO_SECRET_KEY"] == "o"


@pytest.mark.parametrize(
    ("external", "missing"),
    [(AWS, "OSPREY_POSTGRES_PASSWORD"), (AZURE, "AZURE_STORAGE_KEY")],
    ids=["database-password", "storage-key"],
)
def test_a_managed_secret_missing_from_the_environment_is_refused_by_name(
    tmp_path: Path, external: dict[str, Any], missing: str
) -> None:
    env = {"OSPREY_POSTGRES_PASSWORD": "x", "AZURE_STORAGE_KEY": "y"}
    env.pop(missing)
    with pytest.raises(ApplyRefused, match=missing):
        managed_service_lines(_config(tmp_path, external), environ=env, minted="m",
                              object_store_password="o")  # fmt: skip


def test_lite_lines_are_its_own_postgres_and_seaweedfs(tmp_path: Path) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    lines = _lines(managed_service_lines(load_config(path), environ={}, minted="minted",
                                         object_store_password="o"))  # fmt: skip
    assert (lines["POSTGRES_HOST"], lines["POSTGRES_PASSWORD"]) == ("postgres", "minted")
    assert lines["MINIO_ENDPOINT"] == "objectstore:8333"
    assert "POSTGRES_SSLMODE" not in lines and "MINIO_CREDENTIALS" not in lines
