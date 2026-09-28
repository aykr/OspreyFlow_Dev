"""`services/api/credentials.py` — `spec/00_ARCHITECTURE.md` §1.2's "a
reference, never a value".
"""

from __future__ import annotations

import pytest
from services.api.credentials import MissingCredentialError, resolve_env_credential


def test_resolves_a_set_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OS_DATAHUB_API_KEY", "secret-value")

    assert resolve_env_credential("env:OS_DATAHUB_API_KEY") == "secret-value"


def test_raises_naming_the_variable_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_WMTS_KEY", raising=False)

    with pytest.raises(MissingCredentialError) as exc_info:
        resolve_env_credential("env:LOCAL_WMTS_KEY")

    assert exc_info.value.var_name == "LOCAL_WMTS_KEY"
