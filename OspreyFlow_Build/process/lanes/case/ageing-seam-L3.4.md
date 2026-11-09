# Wiring admin's ageing seam to L3.4's promotions (for the orchestrator, at whichever merge comes second)

Admin's L2.6 (on `lane/admin`, its `promotion_ageing` module, not yet on main) reads promotions through
`WaitingPromotions` and fills `app.state.waiting_promotions` with `NoPromotionsYet` until L3.4. L3.4
provides `services/api/promotion_store.py`'s `WaitingFromStore`, which answers
`waiting_for_review(reader)` from `PostgresPromotionStore.waiting(unit=…, markings=…)`, filtered in the
query (rule 3; `test_promotion_store.py`'s `test_the_waiting_read_is_filtered_by_unit_and_clearance_in_the_query`),
and `all_waiting()` for the sweep. It imports nothing of admin's: the seam's record is handed in as
`pending`.

In `services/api/app.py`'s lifespan, replace admin's line

```python
    app.state.waiting_promotions = promotion_ageing_module.NoPromotionsYet()
```

with

```python
    # ADR-145 Amendment 6's seam, answered by L3.4's promotion record (ADR-143 Amendment 5).
    app.state.waiting_promotions = WaitingFromStore(
        store=promotion_store,
        datasets=datasets_store,
        pending=promotion_ageing_module.PendingPromotion,
        clears=lambda clearance: (
            list(scheme.classification[: scheme.classification.index(clearance) + 1])
            if clearance in scheme.classification
            else []
        ),
    )
```

(`promotion_store` is L3.4's `PostgresPromotionStore`, already connected in the lifespan; `scheme` the
deployment's `HandlingScheme`; `from .promotion_store import WaitingFromStore`). `PendingPromotion`'s
fields are exactly what `WaitingFromStore._as_pending` passes: `promotion_id`, `load_id`,
`dataset_id`, `dataset_name`, `dataset_unit`, `proposed_by`, `proposed_at`, `dataset_marking`
(`test_promotions.py`'s `test_the_waiting_seam_lists_only_the_readers_unit_and_clearance` builds it
with the same keywords).

The sweep: admin's `promotion_ageing.sweep` runs wherever admin scheduled it; nothing in L3.4 calls it.
A test to add with the wiring, in admin's `test_promotion_ageing.py`: a promotion sent for review in
L3.4's store and aged past N days raises exactly one *Promotions overdue* alert, to the dataset's
Authors holding `review_promotions` and not its proposer; red with `NoPromotionsYet` left in place.
