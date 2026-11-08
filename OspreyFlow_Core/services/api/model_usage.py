"""*Admin › Models*' usage (`06_DECISIONS.md` ADR-135 Amendment 3 decision 1): calls and tokens per
engine and per job over a chosen period, from the model gateway's own records.

**Counts only** (decision 3): the gateway's records are read through `usage.read_usage`, which
keeps only tags of the Conduit's own `osprey:<engine>/<job>` shape and only their figures. No
prompt, answer, key, person or source-system identifier is in what the gateway keeps for a call
(measured), in what the Conduit sends it, or in this view. There is no figure per person (the
orchestrator's settlement Q3, 8 November 2026): the Conduit sends the gateway no person's id.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from adapters.model_litellm.usage import UsageRecord, read_usage
from schemas.model_admin import ModelUsageView, UsageFigures, UsageRow

from .model_admin import ModelAdmin, ModelAdminRefused
from .model_routing import LOCAL, LOCAL_LABEL

#: The longest period read at once, in days. Longer is refused in words, never cut short.
MAX_PERIOD_DAYS = 366


def check_period(start: date, end: date) -> None:
    if start > end:
        raise ModelAdminRefused("The period's first day must be on or before its last day.")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise ModelAdminRefused(
            f"A period is at most {MAX_PERIOD_DAYS} days; choose a shorter one."
        )


def _add(into: UsageFigures, figures: UsageFigures) -> UsageFigures:
    names = UsageFigures.model_fields
    return UsageFigures(**{f: getattr(into, f) + getattr(figures, f) for f in names})


def build_view(
    records: Sequence[UsageRecord], labels: Mapping[str, str], start: date, end: date
) -> ModelUsageView:
    """The view of `records`: one row per engine and job, and the sums by engine, by job and in
    all. An engine no longer on the deployment keeps its rows, named as removed."""
    rows: list[UsageRow] = []
    by_engine: dict[str, UsageFigures] = {}
    by_job: dict[str, UsageFigures] = {}
    total = UsageFigures()
    for record in records:
        figures = UsageFigures(**dict(record.figures))
        label = labels.get(record.engine) or f"{record.engine} (no longer on this deployment)"
        rows.append(UsageRow(engine=record.engine, engine_label=label, job=record.job,
                             figures=figures))  # fmt: skip
        by_engine[record.engine] = _add(by_engine.get(record.engine, UsageFigures()), figures)
        by_job[record.job] = _add(by_job.get(record.job, UsageFigures()), figures)
        total = _add(total, figures)
    return ModelUsageView(
        start=start, end=end, rows=rows, by_engine=by_engine, by_job=by_job, total=total
    )


async def usage_view(admin: ModelAdmin, start: date, end: date) -> ModelUsageView:
    check_period(start, end)
    records = await read_usage(admin.gateway_http, start, end)
    labels = {LOCAL: LOCAL_LABEL, **{p.name: p.label or p.name for p in admin.settings.providers}}
    return build_view(records, labels, start, end)
