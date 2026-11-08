"""`05_DEPLOYMENT.md` §2.1: the set-up console's Models screen shows the egress exception a
configuration declares ("consequences are shown, not described"), and `04_VAULT_BACKEND.md` §4's
egress is off unless something turns it on.

**The defect these cases pin (platform lane, brief P1, 8 November 2026):** `_egress_consequence`
read only the legacy `models.hosted_fallback`, which ADR-114 Amendment 6 and ADR-135 replaced with
`models.provider` and `models.providers`. A provider set the new way — the only way the schema now
accepts alongside a provider — showed "No egress exception." while case content could leave for
it. Each case goes through the real route the screen calls (`POST /api/consequences`), with the
body shape the screen sends (a whole `OspreyConfig`).
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from harness.webapp import create_app


def _consequences(tmp_path: Any, models: dict[str, Any]) -> dict[str, Any]:
    client = TestClient(
        create_app(config_path=tmp_path / "osprey.yaml"), client=("127.0.0.1", 51000)
    )
    response = client.post("/api/consequences", json={"models": models})
    assert response.status_code == 200, response.text
    return response.json()


def test_providers_set_the_new_way_show_their_egress_exception(tmp_path: Any) -> None:
    body = _consequences(
        tmp_path,
        {
            "local_only": False,
            "sendable_handling_codes": ["O"],
            "providers": [
                {"name": "gemini", "roles": {"extraction": "gemini/gemini-2.5-flash"}},
                {
                    "name": "openai",
                    "label": "Contracted OpenAI",
                    "roles": {"extraction": "openai/gpt-4o-mini"},
                    "privacy_contract": True,
                    "contract_reference": "DPA 2026/07",
                },
            ],
        },
    )
    assert body["egress_exception"] is True
    detail = body["egress_detail"]
    assert "[O]" in detail
    assert "Gemini" in detail and "Contracted OpenAI" in detail
    # ADR-136 decision 1: the contract mark is shown wherever the provider is.
    assert "no contract" in detail and "under contract (DPA 2026/07)" in detail


def test_the_single_older_provider_shows_its_egress_exception(tmp_path: Any) -> None:
    body = _consequences(
        tmp_path,
        {
            "local_only": False,
            "sendable_handling_codes": ["O"],
            "provider": {"name": "anthropic", "roles": {"extraction": "anthropic/claude-x"}},
        },
    )
    assert body["egress_exception"] is True
    assert "Anthropic" in body["egress_detail"]


def test_a_provider_with_no_sendable_codes_still_says_nothing_is_sent(tmp_path: Any) -> None:
    """A provider is enabled but no handling code may leave: no material reaches it, and the
    screen says so rather than claiming either "no exception" or an exception for every code."""
    body = _consequences(
        tmp_path,
        {
            "local_only": False,
            "providers": [{"name": "gemini", "roles": {"extraction": "gemini/gemini-2.5-flash"}}],
        },
    )
    assert body["egress_exception"] is True
    assert "no handling code is sendable" in body["egress_detail"]


def test_the_legacy_hosted_fallback_still_shows_its_exception(tmp_path: Any) -> None:
    body = _consequences(
        tmp_path,
        {"local_only": False, "hosted_fallback": "openai", "sendable_handling_codes": ["O"]},
    )
    assert body["egress_exception"] is True
    assert "'openai'" in body["egress_detail"]


def test_local_only_has_no_egress_exception(tmp_path: Any) -> None:
    body = _consequences(tmp_path, {})
    assert body["egress_exception"] is False
    assert body["egress_detail"] is None
