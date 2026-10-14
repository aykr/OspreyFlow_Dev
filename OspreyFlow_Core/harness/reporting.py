"""The deployment's reporting components (`06_DECISIONS.md` ADR-111 Amendment 2): `report-sync`
and Superset, each a container of its own with its own memory limit, both off by default
(`reporting:` in `osprey.yaml`). Kept apart from `render.py` so each piece — the compose stanzas,
the non-secret settings and the apply-time secrets — is a pure function with its own tests.

Superset sits outside the three tiers: it reads only the reporting mart, through a read-only login,
and signs people in through the deployment's identity provider. `report-sync` runs the Conduit's own
image with another command — the same code, not a second copy.
"""

from __future__ import annotations

import secrets

from harness.site import sites
from schemas.deployment import OspreyConfig


def reporting_services(
    config: OspreyConfig, *, api_image: str, building: bool
) -> dict[str, object]:
    """The compose stanzas for whichever reporting components `osprey.yaml` switches on."""
    reporting = config.reporting
    services: dict[str, object] = {}
    if reporting.sync:
        services["report-sync"] = {
            "restart": "unless-stopped",
            "image": api_image,
            # The image's own entrypoint is the Conduit's uvicorn, and its healthcheck the
            # Conduit's `/healthz`: both replaced, or the sync never starts nor turns healthy.
            "entrypoint": ["python", "-m", "services.report_sync"],
            "healthcheck": {
                "test": ["CMD", "python", "-m", "services.report_sync", "--health"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 3,
                "start_period": "60s",
            },
            "env_file": ["deployment.env"],
            "mem_limit": reporting.sync_memory,
            "depends_on": {
                name: {"condition": "service_healthy"}
                for name in ("api", "postgres", "valkey", "keycloak")
            },
        }
    if reporting.superset:
        stanza: dict[str, object] = {
            "restart": "unless-stopped",
            # Built here from `deploy/superset`, or the release's own image beside the Conduit's
            # (the same registry and commit; `release.yml` publishes both).
            "image": "osprey/superset:local" if building else _beside(api_image, "superset"),
            "env_file": ["deployment.env"],
            "mem_limit": reporting.superset_memory,
            # No port: reached at `bi.` through the front proxy (ADR-114 Amendment 4).
            "depends_on": {
                name: {"condition": "service_healthy"}
                for name in ("postgres", "keycloak", "valkey")
            },
            "healthcheck": {
                "test": ["CMD", "python", "-c",
                         "import urllib.request as u; "
                         "u.urlopen('http://127.0.0.1:8088/health', timeout=5)"],
                "interval": "15s", "timeout": "10s", "retries": 20, "start_period": "120s",
            },
        }  # fmt: skip
        if building:
            stanza["build"] = {"context": "../../superset", "dockerfile": "Dockerfile"}
        services["superset"] = stanza
    return services


def _beside(api_image: str, service: str) -> str:
    """`<registry>/api:<tag>` → `<registry>/<service>:<tag>`."""
    repository, _, tag = api_image.rpartition(":")
    return f"{repository.rpartition('/')[0]}/{service}:{tag}"


def reporting_env(config: OspreyConfig, *, realm: str = "osprey") -> list[str]:
    """The settings the reporting components read that are not secrets."""
    names = sites(config)
    reporting = config.reporting
    lines: list[str] = []
    if not (reporting.sync or reporting.superset):
        return lines
    lines += ["", "# Reporting (ADR-111 Amendment 2): the mart's reader; the services.",
              "REPORT_MART_READER=osprey_reports_reader"]  # fmt: skip
    if reporting.sync:
        lines += [
            f"REPORT_SYNC_TOKEN_URL=http://keycloak:8080/realms/{realm}"
            "/protocol/openid-connect/token",
            "REPORT_SYNC_CONDUIT_URL=http://api:8000",
            f"REPORT_SYNC_INTERVAL_SECONDS={reporting.sync_interval_seconds}",
        ]
    if reporting.superset:
        lines += [
            f"SUPERSET_PUBLIC_ORIGIN={names.dashboards}",
            f"SUPERSET_IDP_INTERNAL=http://keycloak:8080/realms/{realm}",
            f"SUPERSET_IDP_PUBLIC={names.identity}/realms/{realm}",
            "SUPERSET_RATELIMIT_STORAGE=redis://valkey:6379/5",
            # ADR-111 Amendment 3: Superset framed by the Glass; the Conduit's way in to Superset.
            f"SUPERSET_GLASS_ORIGIN={names.glass}",
            "SUPERSET_INTERNAL_URL=http://superset:8088",
        ]
    return lines


def reporting_secrets(config: OspreyConfig) -> str:
    """Minted at apply time, only for the components switched on — never derived from the
    repository, never printed. A dashboard's own secret is not here: it is registered in the Admin
    area and added to `REPORT_SYNC_DASHBOARDS` by whoever registered it."""
    reporting = config.reporting
    lines: list[str] = []
    if reporting.sync or reporting.superset:
        lines.append(f"REPORT_MART_READER_PASSWORD={secrets.token_urlsafe(24)}")
    if reporting.sync:
        lines.append("REPORT_SYNC_DASHBOARDS=[]")
    if reporting.superset:
        lines += [f"SUPERSET_SECRET_KEY={secrets.token_urlsafe(42)}",
                  f"SUPERSET_OIDC_CLIENT_SECRET={secrets.token_urlsafe(32)}",
                  f"SUPERSET_EMBEDDER_PASSWORD={secrets.token_urlsafe(32)}",
                  f"SUPERSET_GUEST_TOKEN_SECRET={secrets.token_urlsafe(42)}"]  # fmt: skip
    return "".join(f"{line}\n" for line in lines)
