"""The one OpenSearch client (ADR-150 decision 7), for the indexer, the rebuild, the drift check and
the query side (ADR-149).

Its address is `OPENSEARCH_URL` when set (cloud-platform: the namespace's OpenSearch Secret), else
`http://OPENSEARCH_HOST:OPENSEARCH_PORT` (Lite and Small). `OPENSEARCH_SIGNING=sigv4` signs every
request as service `es` in `OPENSEARCH_REGION` with the default AWS credentials (IRSA's web
identity through botocore's chain; the owner's ruling for step 3a, 13 November 2026); `none` or
unset sends unsigned. The index alias is per deployment (`OSPREY_SEARCH_INDEX_ALIAS`, default
`ospreyflow-<OSPREY_DEPLOYMENT_NAME or "default">`), so two installs on one domain never meet.
A private CA bundle named in `SSL_CERT_FILE`, `AWS_CA_BUNDLE` or `REQUESTS_CA_BUNDLE` (first set
wins) is trusted beside the system's own roots (opensearch-py's context loads both); one named but
absent is refused in words."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from opensearchpy import AsyncHttpConnection, AsyncOpenSearch

Signing = Literal["none", "sigv4"]


#: Where a deployment names a private CA bundle (a cluster's own CA, or a TLS-inspecting proxy's),
#: first set wins: OpenSSL's, the AWS SDK's, then `requests`'s. opensearch-py reads only the first.
CA_BUNDLE_VARIABLES = ("SSL_CERT_FILE", "AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE")


class SearchIndexConfigError(ValueError):
    """A setting the client cannot be built from, said in words."""


@dataclass(frozen=True)
class SearchIndexConfig:
    url: str
    signing: Signing
    region: str | None
    alias: str
    #: The CA bundle a deployment names (`CA_BUNDLE_VARIABLES`, first set wins), else None: the
    #: client's own default (`SSL_CERT_FILE`, `SSL_CERT_DIR`, then certifi's public roots).
    ca_certs: str | None = None

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
        ca_certs = None
        for variable in CA_BUNDLE_VARIABLES:
            named = (env.get(variable) or "").strip()
            if named:
                if not os.path.isfile(named):
                    raise SearchIndexConfigError(
                        f"{variable} names {named!r}, which is not a file: the search index's "
                        "client cannot trust the CA bundle it names."
                    )
                ca_certs = named
                break
        return cls(url=url, signing=signing, region=region, alias=alias, ca_certs=ca_certs)  # type: ignore[arg-type]


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


def search_client(
    config: SearchIndexConfig | None = None, *, max_retries: int = 3
) -> AsyncOpenSearch:
    """The client, signed or not as the settings say. `max_retries` is how often a request is sent
    again after a connection error (opensearch-py's default, 3, for the indexer and the rebuild);
    the query side passes 0, so an unreachable index costs one timeout a keystroke, not four."""
    config = config or SearchIndexConfig.from_env()
    kwargs: dict[str, Any] = {
        "hosts": [config.url],
        "connection_class": AsyncHttpConnection,
        "timeout": 30,
        "max_retries": max_retries,
    }
    if config.ca_certs is not None:
        kwargs["ca_certs"] = config.ca_certs
    if config.signing == "sigv4":
        assert config.region is not None
        kwargs["http_auth"] = _sigv4_auth(config.region)
    return AsyncOpenSearch(**kwargs)
