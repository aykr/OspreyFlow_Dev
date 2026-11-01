"""The OpenAPI document, published and versioned (the owner's answer of 1 November 2026; GDS
remediation O1; `spec/03_CONDUIT_MIDDLEWARE.md` §3.0a, `spec/05_DEPLOYMENT.md` §2.6.1).

It is served as `GET /v1/openapi.json`, under `/v1/` so the workspace's own proxy — the one every
other API route reaches the deployment's address through — serves it too, and behind sign-in as
every other `/v1` route is. Its `info.version` is the release the deployment was rendered from:
`OSPREY_RELEASE_VERSION`, which `harness.render.release_version` writes from the checkout's release
tag (ADR-114 Amendment 8) and which Admin → System already shows — never FastAPI's default `0.1.0`.

What a mistake would do, and the case that catches it (rule 12):
- the document served to anyone, signed in or not (rule 4) —
  `test_the_document_is_refused_without_sign_in`, and `test_the_unauthenticated_copies_are_gone`
  for FastAPI's own `/openapi.json`, `/docs` and `/redoc`;
- a version that is not the release (`0.1.0`, or a second source of truth that drifts) —
  `test_the_version_is_the_release_the_deployment_was_rendered_from`, which renders the version
  from a checkout tagged as a release, as an install does, and reads it back through the route;
- the document reachable only inside the API container —
  `test_the_workspace_proxy_carries_it_to_the_deployments_address`.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from harness.render import release_version
from services.api.app import app, get_principal
from tools.layout import CORE

from schemas.deployment import OspreyConfig
from schemas.domain import Principal
from tests.harness.test_render import FIXTURE_CONFIG

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-a", roles=["analyst"])


@asynccontextmanager
async def _no_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides[get_principal] = lambda: ANALYST
    try:
        with TestClient(app, raise_server_exceptions=False) as made:
            yield made
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous


def test_the_document_is_refused_without_sign_in(client: TestClient) -> None:
    del app.dependency_overrides[get_principal]
    response = client.get("/v1/openapi.json")
    assert response.status_code in (401, 403), response.text
    assert "openapi" not in response.text


def test_the_unauthenticated_copies_are_gone(client: TestClient) -> None:
    del app.dependency_overrides[get_principal]
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404, path


def _tagged_checkout(tmp_path: Path, tag: str) -> Path:
    repo = tmp_path / "checkout"
    repo.mkdir()
    for args in (("init", "-q"),
                 ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "a"),
                 ("tag", tag)):  # fmt: skip
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)  # noqa: S603, S607
    return repo


def test_the_version_is_the_release_the_deployment_was_rendered_from(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = OspreyConfig.model_validate(yaml.safe_load(FIXTURE_CONFIG))
    config.components.source_path = str(_tagged_checkout(tmp_path, "v0.4.1"))
    rendered = release_version(config)  # what `deployment.env` carries as OSPREY_RELEASE_VERSION
    assert rendered == "v0.4.1"
    monkeypatch.setenv("OSPREY_RELEASE_VERSION", rendered)
    response = client.get("/v1/openapi.json")
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["openapi"].startswith("3.")
    assert document["info"]["version"] == "v0.4.1"
    assert document["info"]["title"] == "OspreyFlow Conduit"
    # The document describes the API itself, and not its own route.
    assert "/v1/investigations" in document["paths"]
    assert "/v1/openapi.json" not in document["paths"]


def test_a_deployment_with_no_release_says_so_rather_than_0_1_0(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OSPREY_RELEASE_VERSION", raising=False)
    monkeypatch.delenv("OSPREY_VERSION", raising=False)
    version = client.get("/v1/openapi.json").json()["info"]["version"]
    assert version == "dev-unknown"


def test_the_workspace_proxy_carries_it_to_the_deployments_address() -> None:
    """The workspace's nginx is what the deployment's address reaches (Caddy proxies the site to
    it); its `/v1/` location sends every `/v1` path to the Conduit, `/v1/openapi.json` included."""
    template = (CORE / "apps" / "workspace" / "nginx.conf.template").read_text(encoding="utf-8")
    block = re.search(r"location /v1/ \{(.*?)\n    \}", template, re.S)
    assert block is not None, "the workspace proxies /v1/"
    assert "proxy_pass $conduit$request_uri;" in block.group(1)
