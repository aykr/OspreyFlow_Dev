"""Saved patterns on their own schedule (`06_DECISIONS.md` ADR-146 decision 4, gap map G16): a
watched pattern runs by every load into its dataset (`evaluation.evaluate_monitors_for_entry`) and
also on its own schedule, daily at 06:00 Europe/London by default, set per watch (`every`, `hour`,
`weekday`; `never` runs it only as data loads), as `rule_schedule.py` runs sentence rules.

**Each slot, judged once, as the watch's owner resolved afresh** (ADR-036, never as the system):
- **one replica per slot**: the latest due slot is claimed with Valkey `SET NX`; earlier slots,
  after downtime, are skipped, not run;
- **as its owner**, resolved afresh by the identity provider and confined to the watch's dataset, so
  it alerts only on what its owner may see (rule 3): an owner who can no longer sign in stops the
  watch (`stopped`, shown on the watch, ADR-036), and one who no longer holds a level on any case
  reading the dataset is matched over nothing;
- the same match, and the same overlap guard, as a load's (`evaluation.match_monitor_guarded`): an
  alert is raised only for a match unlike the last one raised.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply
from principal_auth import PrincipalExchangeUnavailable, PrincipalRevoked
from schemas.domain import Alert, Monitor, Principal, WatchStatus

from .scheduler import DEFAULT_TIMEZONE, due_slots

log = logging.getLogger(__name__)

_CLAIM_SECONDS = 7 * 86400


def monitor_cron(monitor: Monitor) -> str | None:
    """The watch's schedule as the pipeline scheduler's five fields, or `None` for `never`."""
    if monitor.every == "never":
        return None
    day = "*" if monitor.every == "daily" else str((monitor.weekday or 1) % 7)
    return f"0 {monitor.hour} * * {day}"


class ScheduledMonitors(Protocol):
    async def list_all_active(self) -> list[Monitor]: ...
    async def last_slot(self, monitor_id: str) -> datetime | None: ...
    async def record_slot(self, monitor_id: str, slot: datetime) -> None: ...
    async def set_status(self, monitor_id: str, status: WatchStatus) -> None: ...


@dataclass
class MonitorScheduleExecutor:
    """Each tick, every active watched pattern with a slot due is matched once, as its owner."""

    monitors: ScheduledMonitors
    valkey: Valkey
    #: `PrincipalResolver.resolve_for_owner_detailed`: raises, so a revoked owner stops the watch.
    resolve_owner: Callable[[str], Awaitable[Principal]]
    #: Matches the watch as its owner and raises what it finds (`match_monitor_guarded`).
    match: Callable[[Monitor, Principal], Awaitable[list[Alert]]]
    #: Whether the owner, as resolved, still reaches the watch's dataset (a level on a case reading
    #: it, `owner_reaches_dataset_in`): the schedule never reads a dataset its owner has lost.
    reaches_dataset: Callable[[Principal, str], Awaitable[bool]]

    async def tick(self, now: datetime) -> None:
        for monitor in await self.monitors.list_all_active():
            try:
                await self._consider(monitor, now)
            except Exception:  # noqa: BLE001 - one watch's trouble never stops the others
                log.exception("the schedule of watch %s could not be run", monitor.id)

    async def _consider(self, monitor: Monitor, now: datetime) -> None:
        cron = monitor_cron(monitor)
        if cron is None or monitor.status != "active":
            return
        after = await self.monitors.last_slot(monitor.id) or monitor.created_at
        slots = due_slots(cron, DEFAULT_TIMEZONE, after=after, until=now)
        if not slots:
            return
        latest = slots[-1]
        claim = f"monitor-schedule:claim:{monitor.id}:{latest.isoformat()}"
        if not await reply(self.valkey.set(claim, "1", nx=True, ex=_CLAIM_SECONDS)):
            return
        try:
            owner = await self.resolve_owner(monitor.owner_id)
        except PrincipalRevoked:
            await self.monitors.record_slot(monitor.id, latest)
            await self.monitors.set_status(monitor.id, "stopped")
            return
        except PrincipalExchangeUnavailable:
            # Says nothing about the owner: the claim is given back, so the next tick tries the
            # same slot again rather than losing it.
            log.warning("watch %s: the identity provider could not be reached", monitor.id)
            await reply(self.valkey.delete(claim))
            return
        await self.monitors.record_slot(monitor.id, latest)
        if monitor.dataset_id is None:
            return  # no dataset, nothing to read
        # Narrowed to the watch's dataset only once the owner is shown still to reach it: an owner
        # who has lost every case reading it is matched over nothing, and the slot is spent (the
        # watch is not stopped: a case given back runs it again).
        if not await self.reaches_dataset(owner, monitor.dataset_id):
            log.info("watch %s: its owner no longer reaches its dataset", monitor.id)
            return
        await self.match(monitor, owner.model_copy(update={"datasets": [monitor.dataset_id]}))


def monitor_matcher(state: Any) -> Callable[[Monitor, Principal], Awaitable[list[Alert]]]:
    """The running Conduit's match, over its own stores."""
    from .evaluation import match_monitor_guarded

    async def match(monitor: Monitor, owner: Principal) -> list[Alert]:
        return await match_monitor_guarded(
            monitor, owner, graph=state.graph, monitor_store=state.monitors_store,
            pattern_store=state.patterns_store, alert_store=state.alerts_store, audit=state.audit,
            valkey=state.valkey, investigation_id=None,
        )  # fmt: skip

    return match


__all__ = ["MonitorScheduleExecutor", "monitor_cron", "monitor_matcher"]
