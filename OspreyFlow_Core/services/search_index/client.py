"""The one OpenSearch client (ADR-150 decision 7), for the indexer, the rebuild, the drift check and
the query side (ADR-149).

Its address is `OPENSEARCH_URL` when set (cloud-platform: the namespace's OpenSearch Secret), else
`http://OPENSEARCH_HOST:OPENSEARCH_PORT` (Lite and Small). `OPENSEARCH_SIGNING=sigv4` signs every
request as service `es` in `OPENSEARCH_REGION` with the default AWS credentials (IRSA's web
identity through botocore's chain; the owner's ruling for step 3a, 13 November 2026); `none` or
unset sends unsigned. The index alias is per deployment (`OSPREY_SEARCH_INDEX_ALIAS`, default
`ospreyflow-<OSPREY_DEPLOYMENT_NAME or "default">`), so two installs on one domain never meet."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from opensearchpy import AsyncHttpConnection, AsyncOpenSearch

Signing = Literal["none", "sigv4"]


class SearchIndexConfigError(ValueError):
    """A setting the client cannot be built from, said in words."""


@dataclass(frozen=True)
class SearchIndexConfig:
    url: str
    signing: Signing
    region: str | None
    alias: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SearchIndexConfig:
        env = os.environ if environ is None else environ
        url = (env.get("OPENSEARCH_URL") or "").strip()
        if not url:
            host = env.get("OPENSEARCH_HOST") or "localhost"
            port = env.get("OPENSEARCH_PORT") or "9200"
            url = f"http://{host}:{port}"
        signing = (env.get("OPENSEARCH_SIGNING") or "none").strip().lower()
        if signing not in ("none", "sigv4"):
            raise SearchIndexConfigError(
                f"OPENSEARCH_SIGNING is {signing!r}: it must be sigv4 or none."
            )
        region = (env.get("OPENSEARCH_REGION") or "").strip() or None
        if signing == "sigv4" and region is None:
            raise SearchIndexConfigError(
                "OPENSEARCH_SIGNING is sigv4, so OPENSEARCH_REGION must be set."
            )
        alias = (env.get("OSPREY_SEARCH_INDEX_ALIAS") or "").strip()
        if not alias:
            alias = f"ospreyflow-{(env.get('OSPREY_DEPLOYMENT_NAME') or 'default').strip().lower()}"
        return cls(url=url, signing=signing, region=region, alias=alias)  # type: ignore[arg-type]


def _sigv4_auth(region: str) -> Any:
    """AWS SigV4 for service `es`, from botocore's default credential chain (IRSA's web identity on
    the cluster). Imported here so Lite and Small never load botocore for search."""
    import botocore.session
    from opensearchpy import AWSV4SignerAsyncAuth

    credentials = botocore.session.Session().get_credentials()
    if credentials is None:
        raise SearchIndexConfigError(
            "OPENSEARCH_SIGNING is sigv4 but no AWS credentials were found (on the cluster, "
            "the pod's service account must carry the namespace's IAM role)."
        )
    return AWSV4SignerAsyncAuth(credentials, region, "es")


def search_client(config: SearchIndexConfig | None = None) -> AsyncOpenSearch:
    """The client, signed or not as the settings say."""
    config = config or SearchIndexConfig.from_env()
    kwargs: dict[str, Any] = {
        "hosts": [config.url],
        "connection_class": AsyncHttpConnection,
        "timeout": 30,
    }
    if config.signing == "sigv4":
        assert config.region is not None
        kwargs["http_auth"] = _sigv4_auth(config.region)
    return AsyncOpenSearch(**kwargs)
