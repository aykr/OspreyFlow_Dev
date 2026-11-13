"""ADR-150 decision 7: the client's settings, offline."""

from __future__ import annotations

import pytest

from services.search_index.client import SearchIndexConfig, SearchIndexConfigError


def test_lite_and_small_read_host_and_port_unsigned() -> None:
    config = SearchIndexConfig.from_env({"OPENSEARCH_HOST": "opensearch", "OPENSEARCH_PORT": "9200"})
    assert (config.url, config.signing) == ("http://opensearch:9200", "none")


def test_the_url_wins_over_host_and_port() -> None:
    config = SearchIndexConfig.from_env(
        {"OPENSEARCH_URL": "https://vpc-x.eu-west-2.es.amazonaws.com", "OPENSEARCH_PORT": "9200",
         "OPENSEARCH_SIGNING": "sigv4", "OPENSEARCH_REGION": "eu-west-2"}
    )  # fmt: skip
    assert config.url == "https://vpc-x.eu-west-2.es.amazonaws.com"
    assert (config.signing, config.region) == ("sigv4", "eu-west-2")


def test_sigv4_without_a_region_and_an_unknown_signing_are_refused_in_words() -> None:
    with pytest.raises(SearchIndexConfigError, match="OPENSEARCH_REGION"):
        SearchIndexConfig.from_env({"OPENSEARCH_SIGNING": "sigv4"})
    with pytest.raises(SearchIndexConfigError, match="sigv4 or none"):
        SearchIndexConfig.from_env({"OPENSEARCH_SIGNING": "basic"})


def test_the_alias_is_the_deployments_own() -> None:
    assert SearchIndexConfig.from_env({}).alias == "ospreyflow-default"
    assert SearchIndexConfig.from_env({"OSPREY_DEPLOYMENT_NAME": "GovUK"}).alias == "ospreyflow-govuk"
    assert SearchIndexConfig.from_env({"OSPREY_SEARCH_INDEX_ALIAS": "x"}).alias == "x"


def test_the_query_side_can_ask_for_no_retries() -> None:
    """opensearch-py sends a request again after a connection error, three times by default: the
    query side passes 0, so an unreachable index costs one timeout a keystroke, not four."""
    from services.search_index.client import search_client

    config = SearchIndexConfig.from_env({"OPENSEARCH_HOST": "h"})
    assert search_client(config).transport.max_retries == 3
    assert search_client(config, max_retries=0).transport.max_retries == 0
