"""The reporting components' deployment pieces (`06_DECISIONS.md` ADR-111 Amendment 2): off by
default; when on, each its own container with its own memory limit; Superset published on loopback
only; secrets minted only for what is switched on and never in the deterministic render."""

from __future__ import annotations

from harness.reporting import reporting_env, reporting_secrets, reporting_services

from schemas.deployment import OspreyConfig


def _config(**reporting: object) -> OspreyConfig:
    return OspreyConfig.model_validate({"network": {"public_origin": "http://localhost:8080"}, "reporting": reporting})


def test_nothing_is_added_by_default() -> None:
    config = _config()
    assert reporting_services(config, api_image="osprey/api:local", building=True) == {}
    assert reporting_env(config) == [] and reporting_secrets(config) == ""


def test_each_component_is_its_own_container_with_its_own_memory() -> None:
    config = _config(sync=True, superset=True, superset_memory="2g", sync_memory="256m")
    services = reporting_services(config, api_image="osprey/api:local", building=True)
    sync, superset = services["report-sync"], services["superset"]
    assert sync["image"] == "osprey/api:local"  # type: ignore[index]
    # The Conduit's image starts uvicorn and checks `/healthz`: a `command` alone would be handed to
    # uvicorn as options, and the inherited healthcheck could never pass (found live, 11 Oct 2026).
    assert sync["entrypoint"] == ["python", "-m", "services.report_sync"] and "command" not in sync  # type: ignore[index,operator]
    assert sync["healthcheck"]["test"] == ["CMD", "python", "-m", "services.report_sync", "--health"]  # type: ignore[index]
    assert (sync["mem_limit"], superset["mem_limit"]) == ("256m", "2g")  # type: ignore[index]
    assert superset["ports"] == ["127.0.0.1:${OSPREY_SUPERSET_PORT:-8088}:8088"], "loopback only"  # type: ignore[index]
    assert superset["build"] == {"context": "../../superset", "dockerfile": "Dockerfile"}  # type: ignore[index]


def test_the_render_carries_no_secret_and_apply_mints_only_what_is_on() -> None:
    config = _config(sync=True, superset=True)
    env = "\n".join(reporting_env(config))
    assert "SUPERSET_PUBLIC_ORIGIN=http://localhost:8088" in env
    assert "SUPERSET_IDP_PUBLIC=http://localhost:8081/realms/osprey" in env
    # ADR-111 Amendment 3: framed only by the Glass's own origin; the Conduit reaches it inside.
    assert "SUPERSET_GLASS_ORIGIN=http://localhost:8080" in env
    assert "SUPERSET_INTERNAL_URL=http://superset:8088" in env
    assert "PASSWORD" not in env and "SECRET" not in env
    minted = reporting_secrets(config)
    assert {line.split("=")[0] for line in minted.splitlines()} == {
        "REPORT_MART_READER_PASSWORD", "REPORT_SYNC_DASHBOARDS", "SUPERSET_SECRET_KEY", "SUPERSET_OIDC_CLIENT_SECRET",
        "SUPERSET_EMBEDDER_PASSWORD", "SUPERSET_GUEST_TOKEN_SECRET"}  # fmt: skip
    assert reporting_secrets(config) != minted, "freshly minted each time, never derived"
    sync_only = reporting_secrets(_config(sync=True))
    assert "SUPERSET" not in sync_only
