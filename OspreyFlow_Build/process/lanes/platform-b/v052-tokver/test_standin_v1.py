"""ADR-148 Amendment 18 against R1's Entra stand-in issuing v1.0 access tokens: `standin_v1.diff` (platform's
file, sent as a diff) applied to a copy of `process/lanes/platform/gates/r1_kind_servers.py`, the copy run, a
Glass sign-in by code and PKCE made against it, and its access token given to the Conduit's own resolver as
the poc render configures it (v2.0). The refusal must be the version words; with the stand-in at v2.0 the same
sign-in resolves.

    .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider \\
        ../OspreyFlow_Build/process/lanes/platform-b/v052-tokver/test_standin_v1.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from services.api.auth import PrincipalResolver

from principal_auth import ClaimMapping, TokenVersionMismatch
from tests.harness.test_cloud_platform_render import _config, _values
from tests.services.api.test_auth import _config as _api_config
from tests.services.api.test_auth_entra_claims import FakePeople
from tests.test_r1_entra_standin import ACCESS, CONFIG, GLASS, GLASS_REDIRECT, TENANT, _glass_code, _post, _token_url

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[3]
GATES = "OspreyFlow_Build/process/lanes/platform/gates/r1_kind_servers.py"


def _patched(tmp: Path) -> Any:
    """Platform's stand-in with the diff applied, in a folder of the test's own."""
    root = tmp / "tree"
    (root / Path(GATES).parent).mkdir(parents=True)
    shutil.copy2(BUILD.parent / GATES, root / GATES)
    done = subprocess.run(["patch", "-p1", "-i", str(HERE / "standin_v1.diff")], cwd=root, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    spec = importlib.util.spec_from_file_location("r1_kind_servers_v1", root / GATES)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def standin_of(tmp_path: Path) -> Iterator[Any]:
    module, servers = _patched(tmp_path), []

    def start(version: str) -> str:
        config = {**CONFIG, "api": {**CONFIG["api"], "access_token_version": version}}
        server = module.make_server("entra", config, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _glass_token(base: str) -> str:
    code, verifier = _glass_code(base)
    status, answer = _post(_token_url(base), {
        "grant_type": "authorization_code", "client_id": GLASS, "code": code,
        "redirect_uri": GLASS_REDIRECT, "code_verifier": verifier, "scope": f"openid profile {ACCESS}",
    })  # fmt: skip
    assert status == 200, answer
    return str(answer["access_token"])


def _resolve(base: str, token: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    environment = _values(_config("poc"))["environment"]
    monkeypatch.setenv("OSPREY_CLAIM_MAPPING", environment["OSPREY_CLAIM_MAPPING"])
    config = _api_config(f"{base}/{TENANT}/discovery/v2.0/keys", oidc_issuer=environment["OIDC_ISSUER"],
                         oidc_audience=environment["OIDC_AUDIENCE"])  # fmt: skip
    resolver = PrincipalResolver(config, claim_mapping=ClaimMapping.from_env(), role_source=FakePeople())
    return asyncio.run(resolver.resolve_principal(token))


def test_the_stand_in_at_v1_is_refused_in_the_version_s_own_words(standin_of: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    base = standin_of("1.0")
    with pytest.raises(TokenVersionMismatch) as refused:
        _resolve(base, _glass_token(base), monkeypatch)
    assert "issues v1.0 access tokens" in str(refused.value) and "requestedAccessTokenVersion to 2" in str(refused.value)
    assert refused.value.issuer == f"https://sts.windows.net/{TENANT}/"


def test_the_same_sign_in_at_v2_resolves(standin_of: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    base = standin_of("2.0")
    assert _resolve(base, _glass_token(base), monkeypatch).clearance == "OFFICIAL-SENSITIVE"
