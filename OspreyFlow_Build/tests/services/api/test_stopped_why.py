"""ADR-044 Amendment 1: a stopped hotlist or watch says why. The reason is kept beside the binary status
when it is stopped (ADR-044's decision: `status_detail`), cleared when it is active, and served with
its words for the owner, never an id (rule 7). Every stop says one: a load that cannot act as the
owner (each refusal `resolve_for_owner_detailed` raises, its reason), a watch's pattern no longer
theirs, a watch's schedule finding its owner revoked.

Offline: the stores are fakes recording what `set_status` is told; the real stores' column and words
are live cases in `test_hotlists.py` and `test_monitors.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from services.api.evaluation import evaluate_hotlists_for_entry, evaluate_monitors_for_entry, match_monitor
from services.api.monitor_schedule import MonitorScheduleExecutor
from services.api.pattern_store import PatternNotFoundError
from services.api.watch_status import STOPPED_WHY, reason_of, stopped_why

from ontology.handling import load_uk_le_scheme
from principal_auth import (
    ACCESS_OUT_OF_DATE_WORDS,
    OwnerNotHeld,
    OwnerRecordUnavailable,
    PrincipalAccessOutOfDate,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalRevoked,
)
from schemas.domain import Hotlist, Monitor, Principal, StoppedReason
from tests.services.api.test_owner_on_entra import _Claims

OWNER = Principal(id="owner-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
NOW = datetime(2026, 11, 14, 9, tzinfo=UTC)

#: Each refusal the detailed resolver raises, and the reason a stop records for it.
REFUSALS: list[tuple[Exception | None, StoppedReason]] = [
    (PrincipalRevoked("disabled"), "revoked"),
    (PrincipalAccessOutOfDate("owner-1", None), "out_of_date"),
    (OwnerNotHeld("gone"), "not_held"),
    (PrincipalExchangeRefused("refused"), "refused"),
    (PrincipalExchangeUnavailable("down"), "unreachable"),
    (OwnerRecordUnavailable("store down"), "unreachable"),
    (None, "unresolved"),
]
IDS = ["revoked", "out-of-date", "not-held", "refused", "unreachable", "store-unread", "none"]


def _hotlist() -> Hotlist:
    return Hotlist(id="h-1", identifier="07700900123", owner_id=OWNER.id, review_date=date(2027, 1, 1),
                   created_at=NOW)  # fmt: skip


def _monitor() -> Monitor:
    return Monitor(id="m-1", pattern_id="p-1", owner_id=OWNER.id, created_at=NOW - timedelta(days=2),
                   every="daily", hour=5)  # fmt: skip


class _Watches:
    """`HotlistStore`/`MonitorStore` as the evaluator calls them: what `set_status` was told."""

    def __init__(self, active: list[Any]) -> None:
        self.active = active
        self.told: list[tuple[str, str, str | None]] = []

    async def list_all_active(self) -> list[Any]:
        return self.active

    async def set_status(self, watch_id: str, status: str, detail: str | None = None) -> None:
        self.told.append((watch_id, status, detail))

    async def last_slot(self, _id: str) -> None:
        return None

    async def record_slot(self, *_: Any) -> None:
        return None


def _resolving(outcome: Exception | None):  # type: ignore[no-untyped-def]
    async def resolve(_owner: str) -> Principal | None:
        if outcome is None:
            return None
        raise outcome

    return resolve


class _Nothing:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"nothing is read for a watch whose owner cannot be acted as ({name})")


class _Entry(_Nothing):
    """A load's change-stream entry, which a hotlist's evaluation reads the touched ids of first."""

    node_ids: list[str] = ["n-1"]


# --- the words -------------------------------------------------------------------------------------


def test_every_reason_has_its_words_and_none_names_an_id() -> None:
    from typing import get_args

    assert set(STOPPED_WHY) == set(get_args(StoppedReason))
    for reason, words in STOPPED_WHY.items():
        served = stopped_why(reason)  # what a row is served with: the words, whole, and no id
        assert served == words and OWNER.id not in served, reason
        assert not served.lower().startswith("stopped"), reason  # the badge already says it
    assert ACCESS_OUT_OF_DATE_WORDS in STOPPED_WHY["out_of_date"]
    assert "could not be reached" not in " ".join(STOPPED_WHY.values())
    assert stopped_why(None) is None and stopped_why("a-reason-a-later-release-wrote") is None


@pytest.mark.parametrize(("refusal", "reason"), [r for r in REFUSALS if r[0] is not None],
                         ids=[i for i, r in zip(IDS, REFUSALS) if r[0] is not None])  # fmt: skip
def test_each_refusal_is_its_reason(refusal: Exception, reason: str) -> None:
    assert reason_of(refusal) == reason  # type: ignore[arg-type]


# --- every stop records why ------------------------------------------------------------------------


@pytest.mark.parametrize(("refusal", "reason"), REFUSALS, ids=IDS)
async def test_a_load_that_cannot_act_as_a_hotlist_s_owner_stops_it_with_the_reason(
    refusal: Exception | None, reason: str
) -> None:
    store = _Watches([_hotlist()])
    await evaluate_hotlists_for_entry(_Entry(), graph=_Nothing(), scheme=load_uk_le_scheme(), hotlist_store=store,  # type: ignore[arg-type]
                                      alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                      principal_for_owner=_resolving(refusal), policy="strict")  # type: ignore[arg-type]  # fmt: skip
    assert store.told == [("h-1", "stopped", reason)]


@pytest.mark.parametrize(("refusal", "reason"), REFUSALS, ids=IDS)
async def test_a_load_that_cannot_act_as_a_watch_s_owner_stops_it_with_the_reason(
    refusal: Exception | None, reason: str
) -> None:
    store = _Watches([_monitor()])
    await evaluate_monitors_for_entry(_Nothing(), graph=_Nothing(), monitor_store=store, pattern_store=_Nothing(),  # type: ignore[arg-type]
                                      alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                      principal_for_owner=_resolving(refusal))  # fmt: skip
    assert store.told == [("m-1", "stopped", reason)]


async def test_a_watch_whose_pattern_is_no_longer_its_owner_s_stops_with_that_reason() -> None:
    class _Patterns:
        async def get_authorized(self, *_: Any) -> Any:
            raise PatternNotFoundError("p-1")

    store = _Watches([])
    await match_monitor(_monitor(), OWNER, graph=_Nothing(), monitor_store=store, pattern_store=_Patterns(),  # type: ignore[arg-type]
                        alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(), investigation_id=None)  # type: ignore[arg-type]  # fmt: skip
    assert store.told == [("m-1", "stopped", "pattern_gone")]


async def test_a_watch_s_schedule_stops_it_as_revoked_when_its_owner_can_no_longer_sign_in() -> None:
    store = _Watches([])
    executor = MonitorScheduleExecutor(monitors=store, valkey=_Claims(),  # type: ignore[arg-type]
                                       resolve_owner=_resolving(PrincipalRevoked("disabled")),
                                       match=None, reaches_dataset=None)  # type: ignore[arg-type]  # fmt: skip
    watch = _monitor()
    await executor._consider(watch, NOW)
    assert store.told == [("m-1", "stopped", "revoked")]


async def test_a_load_s_watches_are_stopped_with_the_reason_the_detailed_resolver_gives() -> None:
    """Through `recipe_run._evaluate_watches_best_effort`, the call site every load's watches run from:
    another owner's hotlist is stopped with the detailed resolver's reason, and the collapsed form,
    which tells the evaluator nothing, is never asked (a swap back at the call site fails here)."""
    from types import SimpleNamespace

    from services.api.recipe_run import _evaluate_watches_best_effort

    other = Hotlist(id="h-2", identifier="07700900124", owner_id="owner-2", review_date=date(2027, 1, 1),
                    created_at=NOW)  # fmt: skip
    hotlists, monitors = _Watches([other]), _Watches([])
    audited: list[dict[str, Any]] = []

    class _Audit:
        async def record(self, **fields: Any) -> None:
            audited.append(fields)

    class _Resolver:
        async def resolve_for_owner_detailed(self, _o: str) -> Principal:
            raise PrincipalAccessOutOfDate("owner-2", None)

        async def resolve_for_owner(self, _o: str) -> None:
            raise AssertionError("the collapsed form tells the evaluator nothing")

    await _evaluate_watches_best_effort(
        _Entry(), principal=OWNER, graph=_Nothing(), handling_scheme=load_uk_le_scheme(),  # type: ignore[arg-type]
        config=SimpleNamespace(hotlist_alert_policy="strict"), hotlists_store=hotlists,  # type: ignore[arg-type]
        monitors_store=monitors, patterns_store=_Nothing(), alerts_store=_Nothing(), audit=_Audit(),  # type: ignore[arg-type]
        valkey=_Nothing(), investigation_id="case-1", action_on_failure="evaluate_watches_failed",  # type: ignore[arg-type]
        principal_resolver=_Resolver(),  # type: ignore[arg-type]
    )  # fmt: skip
    assert audited == []  # nothing failed
    assert hotlists.told == [("h-2", "stopped", "out_of_date")]


def test_the_user_guide_gives_each_reason_in_the_conduit_s_words() -> None:
    """User guide §7.5 quotes every reason's served sentence whole (rule 12): a reason reworded in the
    code and not the guide, or added without its sentence, fails here."""
    import re
    from pathlib import Path

    guide = (Path(__file__).resolve().parents[4] / "OspreyFlow_Core/docs/user-guide.md").read_text(encoding="utf-8")
    start = guide.index("### 7.5")
    section = re.sub(r"\s+", " ", guide[start : guide.index("\n### ", start + 1)])
    assert [r for r, words in STOPPED_WHY.items() if f'"{words}"' not in section] == []


def test_the_administration_guide_s_troubleshooting_row_quotes_the_unreachable_reason_as_served() -> None:
    """§16 tells an administrator what a hotlist reads when the Conduit cannot act for people: the
    served sentence for `unreachable`, whole."""
    import re
    from pathlib import Path

    guide = (Path(__file__).resolve().parents[4] / "OspreyFlow_Core/docs/administration-guide.md").read_text(encoding="utf-8")
    row = next(line for line in guide.splitlines() if line.startswith('| Rules say "the rule\'s deployer could not be resolved"'))
    assert f'"{STOPPED_WHY["unreachable"]}"' in re.sub(r"\s+", " ", row)


# --- ADR-044's own named tests: the real resolver, a real exchange, to the stored reason --------------


@pytest.fixture
def admin_users_url():  # type: ignore[no-untyped-def]
    """The identity provider's users read, as the pre-check asks it (`users/{id}`): every user known,
    `DISABLED` ones answered `enabled: false`, as Keycloak answers a disabled account."""
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name
            user = self.path.rstrip("/").rsplit("/", 1)[-1]
            body = json.dumps({"id": user, "username": user, "enabled": user not in DISABLED}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/admin/realms/osprey/users"
    finally:
        server.shutdown()


DISABLED = {"owner-disabled"}


async def _stopped_with(resolver: Any, owner_id: str) -> list[tuple[str, str, str | None]]:
    held = Hotlist(id="h-9", identifier="07700900125", owner_id=owner_id, review_date=date(2027, 1, 1),
                   created_at=NOW)  # fmt: skip
    store = _Watches([held])
    try:
        await evaluate_hotlists_for_entry(_Entry(), graph=_Nothing(), scheme=load_uk_le_scheme(), hotlist_store=store,  # type: ignore[arg-type]
                                          alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                          principal_for_owner=resolver.resolve_for_owner_detailed, policy="strict")  # type: ignore[arg-type]  # fmt: skip
    finally:
        await resolver.aclose()
    return store.told


async def test_a_revoked_principal_sets_status_detail_revoked_not_unreachable(
    jwks_url, token_exchange_url, token_exchange_registry, admin_users_url
) -> None:  # type: ignore[no-untyped-def]
    """ADR-044's first named test: the identity provider reached and the account disabled there (the
    Conduit's own pre-check, as against Keycloak), so the hotlist is stopped as `revoked`."""
    from services.api.auth import PrincipalResolver

    from tests.conftest import default_claims
    from tests.services.api.test_auth import _config_with_exchange

    token_exchange_registry.register("owner-disabled", default_claims(sub="owner-disabled"))
    resolver = PrincipalResolver(_config_with_exchange(jwks_url, token_exchange_url,
                                                       oidc_admin_users_url=admin_users_url))  # fmt: skip
    assert await _stopped_with(resolver, "owner-disabled") == [("h-9", "stopped", "revoked")]


async def test_an_unreachable_identity_provider_sets_status_detail_unreachable_not_revoked(jwks_url) -> None:  # type: ignore[no-untyped-def]
    """ADR-044's second named test: the exchange call itself errors (connection refused on a closed
    port), so the hotlist is stopped as `unreachable`, never `revoked`."""
    from services.api.auth import PrincipalResolver

    from tests.services.api.test_auth import _config_with_exchange

    resolver = PrincipalResolver(_config_with_exchange(jwks_url, "http://127.0.0.1:9/token-exchange"))
    assert await _stopped_with(resolver, "owner-1") == [("h-9", "stopped", "unreachable")]


async def test_an_owner_the_identity_provider_refuses_sets_status_detail_refused(
    jwks_url, token_exchange_url
) -> None:  # type: ignore[no-untyped-def]
    """The third case between them: the exchange reached and refused (an account it does not know), so
    `refused`, neither of the two above."""
    from services.api.auth import PrincipalResolver

    from tests.services.api.test_auth import _config_with_exchange

    resolver = PrincipalResolver(_config_with_exchange(jwks_url, token_exchange_url))
    assert await _stopped_with(resolver, "owner-unknown") == [("h-9", "stopped", "refused")]


async def test_a_watch_whose_owner_resolves_is_active_again_though_it_no_longer_reaches_its_dataset() -> None:
    """An earlier reason is never shown once untrue: the owner can be acted as, so the watch is set
    active at once (as a hotlist is), and then skipped, not stopped, for the dataset it no longer reaches."""
    watch = _monitor().model_copy(update={"dataset_id": "ds-1"})
    store = _Watches([watch])

    async def owner(_o: str) -> Principal:
        return OWNER

    async def reaches(_p: Principal, _d: str) -> bool:
        return False

    await evaluate_monitors_for_entry(_Entry(), graph=_Nothing(), monitor_store=store, pattern_store=_Nothing(),  # type: ignore[arg-type]
                                      alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                      principal_for_owner=owner, reaches_dataset=reaches)  # fmt: skip
    assert store.told == [("m-1", "active", None)]
