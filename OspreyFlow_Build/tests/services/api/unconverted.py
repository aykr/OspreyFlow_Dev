"""A case made from another before L3.2, as the data still holds it until
`scripts.migrate_branches_to_views` converts it: it reads its original's dataset and, through
`case_layer_reads`, its original's layer, and holds no layer of its own (ADR-144 Amendment 1). No
route makes one now, so tests that need one make it here, as an L3.1 copy left it.
"""

from __future__ import annotations

from services.api.datasets import InMemoryDatasetStore, PostgresDatasetStore


async def made_before_l3_2(store: InMemoryDatasetStore, original: str, made: str) -> str:
    """Links `made` to `original` as an L3.1 copy did, giving the original its layer first if it
    has none (as the copy did). Returns the original's layer."""
    chosen = list(store.cases.get(original, []))
    layer = await store.layer_of_case(original)
    if layer is None:
        parent = store.datasets[chosen[0]]
        layer = await store.ensure_layer(
            original, unit=parent.owning_unit, created_by=parent.created_by
        )
    store.cases[made] = chosen
    store.layer_reads[made] = layer
    return layer


async def made_before_l3_2_on_postgres(store: PostgresDatasetStore, original: str, made: str) -> str:
    """The same on Postgres: the original's chosen dataset and its layer link, written as the L3.1
    copy wrote them."""
    layer = await store.layer_of_case(original)
    async with store._pool.acquire() as conn:  # noqa: SLF001 - writing what no route writes now
        if layer is None:
            parent = await conn.fetchrow(
                "SELECT d.owning_unit, d.created_by FROM investigation_datasets c "
                "JOIN datasets d ON d.id = c.dataset_id WHERE c.investigation_id = $1 "
                "ORDER BY c.position LIMIT 1",
                original,
            )
            layer = await store.ensure_layer(
                original, unit=parent["owning_unit"], created_by=parent["created_by"]
            )
        await conn.execute(
            "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
            "SELECT $2, c.dataset_id, c.position FROM investigation_datasets c "
            "JOIN datasets d ON d.id = c.dataset_id "
            "WHERE c.investigation_id = $1 AND d.kind <> 'analyst_layer' ON CONFLICT DO NOTHING",
            original,
            made,
        )
        await conn.execute(
            "INSERT INTO case_layer_reads (investigation_id, layer_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            made,
            layer,
        )
    return layer
