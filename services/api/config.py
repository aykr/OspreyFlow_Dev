"""Environment configuration for the Conduit's API process.

Every setting is read from the environment, never hardcoded and never
carried in `osprey.yaml` at this layer — `05_DEPLOYMENT.md` §7: "Secrets
from the environment or a secret manager, never in `osprey.yaml`". Default
values throughout match `packages/adapters/graph_arcadedb/client.py` and
`services/ingest/staging.py`'s own defaults, and `deploy/compose/dev.yaml`
(`make dev-up`) stands up services on exactly those defaults, so the whole
stack runs locally with zero env configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .alerts import DisclosurePolicy, disclosure_policy_from_value
from .export import ExportManifestPolicy, export_manifest_policy_from_value


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


@dataclass(frozen=True)
class ValkeyConfig:
    host: str
    port: int
    db: int

    @classmethod
    def from_env(cls) -> ValkeyConfig:
        return cls(
            host=os.environ.get("VALKEY_HOST", "localhost"),
            port=int(os.environ.get("VALKEY_PORT", "6379")),
            db=int(os.environ.get("VALKEY_DB", "0")),
        )

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    user: str
    password: str
    database: str

    @classmethod
    def from_env(cls) -> PostgresConfig:
        return cls(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            # 5433, not Postgres's usual 5432: deploy/compose/dev.yaml publishes
            # on 5433 to avoid colliding with a native Postgres already bound to
            # 127.0.0.1:5432 on some dev machines. CI's own Postgres service
            # still uses 5432 and sets POSTGRES_PORT explicitly to override this.
            port=int(os.environ.get("POSTGRES_PORT", "5433")),
            user=os.environ.get("POSTGRES_USER", "osprey"),
            password=os.environ.get("POSTGRES_PASSWORD", "playwithdata123"),
            database=os.environ.get("POSTGRES_DB", "ospreyflow"),
        )

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        )


#: `01_DOMAIN_MODEL.md` §8.2: measured at ~41s for a 5,000-degree node —
#: "a request that takes 41 seconds is not a reasonable synchronous
#: operation". Default set well under that, on the side of routing a
#: correction job-based too early rather than too late; a deployment with
#: a slower store tunes it down further, not up.
DEFAULT_SUPERSEDE_JOB_DEGREE_THRESHOLD = 500


@dataclass(frozen=True)
class ApiConfig:
    valkey: ValkeyConfig
    postgres: PostgresConfig
    oidc_jwks_url: str
    oidc_audience: str | None
    oidc_issuer: str | None
    oidc_algorithms: tuple[str, ...]
    oidc_jwks_ttl_seconds: float
    #: `06_DECISIONS.md` ADR-043 — OAuth2 Token Exchange (RFC 8693). `None` (the default, no
    #: environment variable set) means this deployment has not configured exchange:
    #: `PrincipalResolver.resolve_for_owner` then has no path to a non-requester owner and
    #: `services/api/app.py`'s `_principal_for_owner` falls back to the pre-ADR-043 behaviour
    #: (resolves only the requester's own id) rather than raising — the same
    #: "narrower-but-honest" default ADR-036 already commits this codebase to elsewhere, not a
    #: hard requirement every existing deployment/test must satisfy to keep working.
    oidc_token_exchange_url: str | None
    #: The Conduit's own confidential client — ADR-043's own "what that configuration must be":
    #: scoped by the realm's own policy to exchange for an arbitrary subject and nothing broader.
    oidc_token_exchange_client_id: str | None
    oidc_token_exchange_client_secret: str | None
    supersede_job_degree_threshold: int
    #: `osprey.yaml` itself is never a secret (`05_DEPLOYMENT.md` §7) — only
    #: its *path* is environment configuration, the same way a connector's
    #: recipe path is. Relative to the process's working directory, which
    #: `deploy/compose/dev.yaml` and CI both run from the repo root.
    osprey_config_path: str
    #: A persistent (not `:memory:`) DuckDB file. `analytics_duckdb/testing.py`'s own
    #: docstring records
    #: the longer-term intent (Parquet in object storage); this is the
    #: deliberately narrower, already-conformance-tested native-table store
    #: standing in for it, a stated and recorded deferral (this phase's plan
    #: and end-of-checkpoint audit), not silently dropped. The parent
    #: directory is created if it doesn't exist — `deploy/compose/dev.yaml`
    #: bind-mounts nothing for this, since DuckDB is embedded, not a service.
    analytics_db_path: str
    #: `06_DECISIONS.md` ADR-038 — deployment-level, read once at process start, never a per-
    #: request or per-hotlist setting. `services/api/alerts.py::disclosure_policy_from_value`
    #: is what actually enforces the fail-closed default; this field only carries whatever that
    #: function resolved, once, here.
    hotlist_alert_policy: DisclosurePolicy
    #: `06_DECISIONS.md` ADR-045 — deployment-level, the same shape as `hotlist_alert_policy`
    #: above, with the *opposite* fail-closed default (`export_manifest_policy_from_value`'s own
    #: docstring has the reasoning): unset/empty/unrecognised means `disclose`, not `omit`.
    export_manifest_policy: ExportManifestPolicy

    @classmethod
    def from_env(cls) -> ApiConfig:
        jwks_url = os.environ.get("OIDC_JWKS_URL")
        if not jwks_url:
            raise RuntimeError(
                "OIDC_JWKS_URL is not set — Principal resolution has no key source. "
                "Point it at an IdP's JWKS endpoint (http/https only — a bare local file "
                "is not a supported scheme)."
            )
        algorithms = tuple(
            a.strip() for a in os.environ.get("OIDC_ALGORITHMS", "RS256").split(",") if a.strip()
        )
        return cls(
            valkey=ValkeyConfig.from_env(),
            postgres=PostgresConfig.from_env(),
            oidc_jwks_url=jwks_url,
            oidc_audience=os.environ.get("OIDC_AUDIENCE") or None,
            oidc_issuer=os.environ.get("OIDC_ISSUER") or None,
            oidc_algorithms=algorithms,
            oidc_jwks_ttl_seconds=_env_float("OIDC_JWKS_TTL_SECONDS", 300.0),
            oidc_token_exchange_url=os.environ.get("OIDC_TOKEN_EXCHANGE_URL") or None,
            oidc_token_exchange_client_id=os.environ.get("OIDC_TOKEN_EXCHANGE_CLIENT_ID") or None,
            oidc_token_exchange_client_secret=(
                os.environ.get("OIDC_TOKEN_EXCHANGE_CLIENT_SECRET") or None
            ),
            supersede_job_degree_threshold=int(
                os.environ.get(
                    "SUPERSEDE_JOB_DEGREE_THRESHOLD", str(DEFAULT_SUPERSEDE_JOB_DEGREE_THRESHOLD)
                )
            ),
            osprey_config_path=os.environ.get("OSPREY_CONFIG_PATH", "osprey.yaml"),
            analytics_db_path=os.environ.get("ANALYTICS_DB_PATH", "data/analytics.duckdb"),
            hotlist_alert_policy=disclosure_policy_from_value(
                os.environ.get("HOTLIST_ALERT_POLICY")
            ),
            export_manifest_policy=export_manifest_policy_from_value(
                os.environ.get("EXPORT_MANIFEST_POLICY")
            ),
        )
