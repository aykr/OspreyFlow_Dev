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
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from schemas.deployment import ModelsConfig

from .alerts import DisclosurePolicy, disclosure_policy_from_value
from .export import ExportManifestPolicy, export_manifest_policy_from_value


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


#: Where a Conduit run from a checkout keeps its analytics store: the Data folder, never the product
#: tree (ADR-054). Relative to the product folder, where `make` and the seeds run
#: from; the Data folder is its sibling. The seeds
#: and the pre-flight check carry the same string, and `tests/test_data_folder.py` fails if any of
#: them drifts. A deployment sets `ANALYTICS_DB_PATH` itself.
DEFAULT_ANALYTICS_DB_PATH = "../OspreyFlow_Data/_local-runtime/analytics.duckdb"


@dataclass(frozen=True)
class ValkeyConfig:
    """The deployment's own Valkey, or a cloud's managed one (`05_DEPLOYMENT.md` §3b), reached with
    its password (`VALKEY_PASSWORD`) and over TLS (`VALKEY_TLS`)."""

    host: str
    port: int
    db: int
    password: str | None = field(default=None, repr=False)
    tls: bool = False

    @classmethod
    def from_env(cls) -> ValkeyConfig:
        return cls(
            host=os.environ.get("VALKEY_HOST", "localhost"),
            port=int(os.environ.get("VALKEY_PORT", "6379")),
            db=int(os.environ.get("VALKEY_DB", "0")),
            password=os.environ.get("VALKEY_PASSWORD") or None,
            tls=os.environ.get("VALKEY_TLS", "").lower() in {"1", "true", "yes"},
        )

    def client_kwargs(self) -> dict[str, Any]:
        """What the Conduit and the worker both open Valkey with."""
        kwargs: dict[str, Any] = {"host": self.host, "port": self.port, "db": self.db}
        if self.password is not None:
            kwargs["password"] = self.password
        if self.tls:
            kwargs["ssl"] = True
        return kwargs

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
    #: A managed server's TLS requirement (`05_DEPLOYMENT.md` §3a): `require`, `verify-full`…
    sslmode: str | None = None

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
            sslmode=os.environ.get("POSTGRES_SSLMODE") or None,
        )

    @property
    def dsn(self) -> str:
        """Every part escaped: a password a cloud's secret store made may hold any character."""
        user, password = quote(self.user, safe=""), quote(self.password, safe="")
        tls = f"?sslmode={quote(self.sslmode, safe='')}" if self.sslmode else ""
        return (
            f"postgresql://{user}:{password}@{self.host}:{self.port}/"
            f"{quote(self.database, safe='')}{tls}"
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

    #: The IdP's own admin users endpoint, used **only** to read a target principal's `enabled`
    #: status before exchanging for them — ADR-043's amendment of 24 September 2026. A separate
    #: grant from the impersonation one on purpose: the containment this closes is that Keycloak
    #: will mint a token for a *disabled* subject, and a pre-check that shared the impersonation
    #: grant would be checking with the same authority that fails open.
    #:
    #: `None` leaves the pre-check off and the exchange behaves exactly as before, which is what
    #: keeps every existing deployment and test working unchanged.
    oidc_admin_users_url: str | None = None
    #: `components.analytics_engine` (ADR-114 decision 9): `duckdb` or `clickhouse`, opened by
    #: `services/api/analytics_store.py`, which refuses anything else.
    analytics_engine: str = "duckdb"

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
            oidc_admin_users_url=os.environ.get("OIDC_ADMIN_USERS_URL") or None,
            oidc_token_exchange_client_secret=(
                os.environ.get("OIDC_TOKEN_EXCHANGE_CLIENT_SECRET") or None
            ),
            supersede_job_degree_threshold=int(
                os.environ.get(
                    "SUPERSEDE_JOB_DEGREE_THRESHOLD", str(DEFAULT_SUPERSEDE_JOB_DEGREE_THRESHOLD)
                )
            ),
            osprey_config_path=os.environ.get("OSPREY_CONFIG_PATH", "osprey.yaml"),
            analytics_db_path=os.environ.get("ANALYTICS_DB_PATH", DEFAULT_ANALYTICS_DB_PATH),
            analytics_engine=os.environ.get("OSPREY_ANALYTICS_ENGINE", "duckdb"),
            hotlist_alert_policy=disclosure_policy_from_value(
                os.environ.get("HOTLIST_ALERT_POLICY")
            ),
            export_manifest_policy=export_manifest_policy_from_value(
                os.environ.get("EXPORT_MANIFEST_POLICY")
            ),
        )


@dataclass(frozen=True)
class DeploymentModels:
    """The models the Conduit uses for analysts' work — `06_DECISIONS.md` ADR-095. Chosen on the
    setup harness's Models screen, written to `osprey.yaml` and rendered into the deployment's
    environment; a Conduit started without them (a developer's own run) uses the models the product
    ships with. Never the conformance suite's: `test_deployment_models.py` scans for that."""

    extraction: str
    vision: str
    transcription: str
    embedding: str

    @classmethod
    def from_env(cls) -> DeploymentModels:
        shipped = ModelsConfig()
        return cls(
            extraction=os.environ.get("OSPREY_EXTRACTION_MODEL", shipped.extraction),
            vision=os.environ.get("OSPREY_VISION_MODEL", shipped.vision),
            transcription=os.environ.get("OSPREY_TRANSCRIPTION_MODEL", shipped.transcription),
            embedding=os.environ.get("OSPREY_EMBEDDING_MODEL", shipped.embedding),
        )
