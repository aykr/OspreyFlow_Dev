"""A settings change the deployment's schema refuses is answered 422 in words, never 500
(`06_DECISIONS.md` ADR-114 Amendment 3: the guided install page's Enterprise mode sets `profile:
cluster`, which a default configuration's components refuse). Found building the page: the error's
context carried a raw `ValueError`, which JSON cannot carry, so the refusal crashed the server.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from harness.webapp import create_app


def test_a_refused_profile_is_a_422_with_its_reason(tmp_path: Path) -> None:
    config = tmp_path / "osprey.yaml"
    config.write_text("profile: local-lite\n", encoding="utf-8")
    client = TestClient(create_app(config_path=config, out_root=tmp_path / "out", require_sign_in=False),
                        raise_server_exceptions=False, client=("127.0.0.1", 51000))  # fmt: skip
    response = client.put("/api/config", json={"profile": "cluster"})
    assert response.status_code == 422, response.text
    assert "cluster" in response.text or "graph" in response.text.lower()
    assert config.read_text(encoding="utf-8") == "profile: local-lite\n", "nothing written"
