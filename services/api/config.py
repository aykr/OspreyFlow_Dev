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
    supersede_job_degree_threshold: int

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
            supersede_job_degree_threshold=int(
                os.environ.get(
                    "SUPERSEDE_JOB_DEGREE_THRESHOLD", str(DEFAULT_SUPERSEDE_JOB_DEGREE_THRESHOLD)
                )
            ),
        )
