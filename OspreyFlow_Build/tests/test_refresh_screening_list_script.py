"""The operator's refresh of a screening list (`scripts/refresh_screening_list.py`, ADR-133 decision 4)
records its audit entry with the list's marking as it stood (ADR-146 Amendment 7), as the route and
the schedule's refresh do: Admin › Audit admits a reader to an entry naming a list by that marking,
so an entry recording none would read as OFFICIAL, P were the list's kept marking gone (the lane
review of the audit follow-up, item 2).

Offline: the run's resources are stand-ins (`build_run_resources` replaced), the store answering the
marking a real one keeps for the list. Red with the marking left out of the script's write.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from schemas.screening import ScreeningListUpdate

from scripts import refresh_screening_list as script


class _Store:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def audit_marking(self, list_name: str) -> dict[str, str]:
        self.asked.append(list_name)
        return {"list_classification": "SECRET", "list_handling_code": "R"}


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def test_the_operators_refresh_records_the_lists_marking(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    from conduit_common.identity import new_id
    from ontology.handling import load_uk_le_scheme

    store, audit = _Store(), _Audit()

    async def closed() -> None:
        return None

    resources = SimpleNamespace(
        screening_lists=store, audit=audit, handling_scheme=load_uk_le_scheme(), typology_rules=None,
        datasets_store=None, graph=None, alerts_store=None, valkey=None,
        principal_resolver=SimpleNamespace(resolve_for_owner=None), close=closed,
    )  # fmt: skip

    async def built(_config: Any) -> Any:
        return resources

    async def refreshed(list_name: str, **_: Any) -> ScreeningListUpdate:
        return ScreeningListUpdate(id=new_id(), list_name=list_name, at=datetime.now(UTC),
                                   outcome="updated", version="v2", words="Version v2.")  # fmt: skip

    monkeypatch.setattr(script, "build_run_resources", built)
    monkeypatch.setattr(script, "refresh", refreshed)
    monkeypatch.setattr(script.ApiConfig, "from_env", staticmethod(lambda: None))

    assert script.main(["Synthetic list SECRET (operator)"]) == 0
    [entry] = audit.records
    assert entry["action"] == "screening_list_refreshed"
    query = entry["resolved_query"]
    assert query["list_name"] == "Synthetic list SECRET (operator)"
    assert (query["list_classification"], query["list_handling_code"]) == ("SECRET", "R")
    assert store.asked == ["Synthetic list SECRET (operator)"]
