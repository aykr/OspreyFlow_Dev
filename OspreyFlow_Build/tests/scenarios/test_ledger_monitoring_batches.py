"""Operation Ledger's monitoring week, the batch itself (`spec/06_DECISIONS.md` ADR-108 Amendment 5).
Pure: the generator's rows, the seed's own September beside them, and the typologies and screening as
the rules run them — no store.

What a mistake in the generator would do, and the case that catches it:
- a different file on another run, so a rehearsal's numbers drift
  (`test_the_week_is_the_same_every_time`);
- a background row touching an account the story turns on, so an alert names the wrong row or a
  hotlist fires twice (`test_only_the_story_rows_touch_the_storys_accounts`);
- background trading that comes back round, passes money through or looks structured, so a rule
  raises an alert the walkthrough does not show (`test_the_background_never_comes_back_round`);
- the story losing its pass-through or its circle, or gaining a second one from September's flows
  (`test_the_story_makes_one_pass_through_and_one_circle`);
- a column the committed recipe does not read (`test_the_week_is_in_the_recipes_own_columns`);
- the list's version 2 not adding exactly one designation that matches exactly one customer
  (`test_the_list_versions_differ_by_one_designation_matching_one_customer`).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from services.api.screening import ScreeningEntry, screen
from services.api.screening_refresh import entries_of
from services.ingest.recipe_loader import load_recipe
from services.ingest.typologies import MoneyFlow, circular_flows, rapid_movement, structuring

from demo_fixtures import ledger, ledger_monitoring
from demo_fixtures.ledger_monitoring import (
    CARTER_ACC,
    CRESCENT_ACC,
    RUIZ_ACC,
    ZELINSKY_ACC,
    background_rows,
    week_rows,
)
from knowledge_adapters.screening_lists import uk_sanctions_list

LISTS = Path(ledger.__file__).resolve().parent / "screening_lists"


def _flows(rows: list[dict[str, str]], prefix: str) -> list[MoneyFlow]:
    return [
        MoneyFlow(r["payer_iban"], r["payee_iban"], float(r["amount"]),
                  datetime.fromisoformat(r["at"].replace("Z", "+00:00")), f"{prefix}{i}")
        for i, r in enumerate(rows)
    ]  # fmt: skip


def _judged(typology: object, reach: timedelta, rows: list[dict[str, str]]) -> list[object]:
    """As `rule_evaluation.judge` reads: the new flows, September's flows touching their accounts
    within the rule's reach, and only the hits citing a new flow."""
    new = _flows(rows, "n")
    accounts = {f.source for f in new} | {f.target for f in new}
    low, high = min(f.at for f in new) - reach, max(f.at for f in new) + reach
    context = [f for f in _flows(ledger.transaction_rows(), "s")
               if {f.source, f.target} & accounts and low <= f.at <= high]  # fmt: skip
    ids = {f.ref for f in new}
    return [h for h in typology(context + new) if ids & set(h.refs)]  # type: ignore[operator]


def _rapid(rows: list[dict[str, str]]) -> list[object]:
    p = ledger_monitoring.RAPID_MOVEMENT
    return _judged(lambda f: rapid_movement(f, within=timedelta(hours=p["within_hours"]),
                                            keep_fraction=p["keep_fraction"]),
                   timedelta(hours=p["within_hours"]), rows)  # fmt: skip


def _circle(rows: list[dict[str, str]], days: int | None = None) -> list[object]:
    p = ledger_monitoring.CIRCULAR_FLOW
    window = days or p["window_days"]
    return _judged(lambda f: circular_flows(f, max_hops=p["max_hops"]), timedelta(days=window), rows)


def _structured(rows: list[dict[str, str]]) -> list[object]:
    return _judged(lambda f: structuring(f, threshold=10_000, window=timedelta(days=7), minimum_count=3),
                   timedelta(days=7), rows)  # fmt: skip


def test_the_week_is_the_same_every_time(tmp_path: Path) -> None:
    assert week_rows() == week_rows()
    first = ledger_monitoring.write_batches(tmp_path / "a")
    second = ledger_monitoring.write_batches(tmp_path / "b")
    assert [w.sha256 for w in first] == [w.sha256 for w in second]
    assert first[0].rows == 13 and first[0].name == "incoming/ledger_transactions_week2.csv"
    days = {r["at"][:10] for r in week_rows()}
    assert min(days) >= "2026-10-05" and max(days) <= "2026-10-11"
    assert max(r["at"] for r in ledger.transaction_rows()) < min(r["at"] for r in week_rows())


def test_only_the_story_rows_touch_the_storys_accounts() -> None:
    rows = week_rows()
    assert ledger_monitoring.touching(CARTER_ACC, rows) == [
        {"payer_iban": ZELINSKY_ACC, "payee_iban": CARTER_ACC, "amount": "9700",
         "at": "2026-10-09T11:40:00Z", "transaction_type": "CASH_IN"}]  # fmt: skip
    assert len(ledger_monitoring.touching(RUIZ_ACC, rows)) == 2
    assert len(ledger_monitoring.touching(CRESCENT_ACC, rows)) == 2
    assert ledger_monitoring.touching(ledger.HALE_BIZ, rows) == []
    for row in background_rows():
        assert not {row["payer_iban"], row["payee_iban"]} & ledger_monitoring.UNTOUCHED_BY_BACKGROUND


def test_the_background_never_comes_back_round() -> None:
    rows = background_rows()
    assert _rapid(rows) == [] and _circle(rows) == [] and _structured(rows) == []
    kesterton, midland, arden = ledger.TRADING_ACCOUNTS
    assert {(r["payer_iban"], r["payee_iban"]) for r in rows} <= {
        (kesterton, midland), (kesterton, arden), (midland, arden)}  # fmt: skip


def test_the_story_makes_one_pass_through_and_one_circle() -> None:
    rows = week_rows()
    (passed,) = _rapid(rows)
    assert passed.subject == RUIZ_ACC  # type: ignore[attr-defined]
    (circle,) = _circle(rows)
    assert circle.subject == CRESCENT_ACC and len(circle.refs) == 3  # type: ignore[attr-defined]
    assert _structured(rows) == [], "one cash deposit is no ring"
    # With the template's 30 days the circle also finds September's ring going round (Amendment 5's
    # reading 2): why the walkthrough tunes it to a week.
    assert len(_circle(rows, days=30)) > 1


def test_the_week_is_in_the_recipes_own_columns() -> None:
    recipe = load_recipe(Path(ledger.__file__).resolve().parent / ledger_monitoring.RECIPE)
    read = {p.field for e in recipe.row_template.entities for p in e.properties.values() if p.field}
    read |= {p.field for e in recipe.row_template.edges for p in e.properties.values() if p.field}
    read |= {e.temporal.at.field for e in recipe.row_template.edges if e.temporal}  # type: ignore[union-attr]
    assert set(ledger_monitoring.HEADER) == read
    assert set(ledger.transaction_rows()[0]) == set(ledger_monitoring.HEADER)


def _entries(version: str) -> list[ScreeningEntry]:
    parsed = uk_sanctions_list((LISTS / version).read_text(encoding="utf-8"))
    return entries_of(ledger_monitoring.UK_LIST_NAME, parsed, synthetic=True)


def test_the_list_versions_differ_by_one_designation_matching_one_customer() -> None:
    v1, v2 = _entries(ledger_monitoring.UK_LIST_V1), _entries(ledger_monitoring.UK_LIST_V2)
    added = {e.id for e in v2} - {e.id for e in v1}
    assert added == {f"{ledger_monitoring.UK_LIST_NAME}:{ledger_monitoring.UK_LIST_ADDED}"}
    customers = [f"{r['given_names']} {r['family_name']}" for r in ledger.kyc_rows()]
    customers += [r["company_name"] for r in ledger.company_rows()]
    customers += ["Elena Petrov", "Priya Nair", "Tamarind Holdings Ltd", "Aegean Fiduciary Trust",
                  "Kestrel Nominees Ltd", "Halcyon Marine Ltd", "Brookfield Joinery Ltd"]  # fmt: skip
    for name in customers:
        assert screen(name, None, v1, min_score=0.9) == [], f"version 1 must name no customer: {name}"
    found = {name: [h.entry.name for h in screen(name, None, v2, min_score=0.9)] for name in customers}
    assert {n: hits for n, hits in found.items() if hits} == {"Sofia Ruiz": ["RUIZ, Sofia"]}
    (ruiz,) = [e for e in v2 if e.id.endswith(ledger_monitoring.UK_LIST_ADDED)]
    assert str(ruiz.date_of_birth) == next(r["date_of_birth"] for r in ledger.kyc_rows()
                                           if r["family_name"] == "Ruiz")  # fmt: skip
