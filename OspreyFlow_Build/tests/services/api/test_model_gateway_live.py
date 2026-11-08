"""The key round trip against the real, pinned LiteLLM gateway (`06_DECISIONS.md` ADR-135 Amendment 2;
`CLAUDE.md` rule 15): the Conduit's own client (`GatewayAdmin`, `check_connection`) sets a key as a
credential, makes an entry that names it, is refused a wrong key in fixed words, rotates, and
removes the key and the entry, each answered as the stand-in gateway answers.

**Live, so skipped unless pointed at a gateway** (`OSPREY_LIVE_GATEWAY_URL`, its master key in
`OSPREY_LIVE_GATEWAY_MASTER`), with a stand-in provider at `OSPREY_LIVE_PROVIDER_BASE` that accepts
the key `sk-good-provider-key` for the model `known-model` (as `fakeprov.py` in the platform lane's
record does). No hosted provider is ever called, and the keys are synthetic (rule 9). Run under a
test-stack lease; `process/lanes/platform/P1_RED_RECORD.md` has the commands and the result.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest
from adapters.model_litellm.connection import check_connection
from pydantic import SecretStr
from services.api.model_admin import GatewayAdmin, entry_id

from schemas.deployment import ModelProviderConfig

URL = os.environ.get("OSPREY_LIVE_GATEWAY_URL", "")
MASTER = os.environ.get("OSPREY_LIVE_GATEWAY_MASTER", "")
PROVIDER_BASE = os.environ.get("OSPREY_LIVE_PROVIDER_BASE", "")
GOOD = "sk-good-provider-key"
WRONG = "sk-PLANTED-wrong-key-7Q4Z"

pytestmark = pytest.mark.skipif(
    not (URL and MASTER and PROVIDER_BASE),
    reason="live: set OSPREY_LIVE_GATEWAY_URL, OSPREY_LIVE_GATEWAY_MASTER and "
    "OSPREY_LIVE_PROVIDER_BASE (a lease, the pinned gateway, a stand-in provider)",
)


async def test_the_key_round_trip_against_the_real_gateway() -> None:
    http = httpx.AsyncClient(base_url=URL, headers={"Authorization": f"Bearer {MASTER}"})
    gateway = GatewayAdmin(http)
    # Built without validation: the stand-in provider is plain http on the test network.
    provider = ModelProviderConfig.model_construct(
        name="openai", label="Stand-in", roles={"extraction": "known-model"},
        api_base=PROVIDER_BASE, privacy_contract=False, contract_reference=None,
    )  # fmt: skip
    model = "openai/known-model"
    try:
        await gateway.put_credential("openai", SecretStr(WRONG))
        if entry_id("openai", "known-model") not in await gateway.stored_entries():
            await gateway.add_entry(provider, "known-model")
        wrong = await check_connection(http, model)
        assert wrong.outcome == "key_refused" and "7Q4Z" not in wrong.words
        await gateway.put_credential("openai", SecretStr(GOOD))
        assert (await check_connection(http, model)).outcome in {"cooling_down", "ok"}
        await asyncio.sleep(65)  # the gateway's measured cooldown after a failure
        assert (await check_connection(http, model)).outcome == "ok"
        await gateway.delete_credential("openai")
        await asyncio.sleep(65)
        assert (await check_connection(http, model)).outcome == "key_refused"
        await gateway.delete_entry(entry_id("openai", "known-model"))
        assert entry_id("openai", "known-model") not in await gateway.stored_entries()
    finally:
        await gateway.delete_credential("openai")
        await gateway.delete_entry(entry_id("openai", "known-model"))
        await http.aclose()


PG_CONTAINER = os.environ.get("OSPREY_LIVE_PG_CONTAINER", "")
GATEWAY_DB = os.environ.get("OSPREY_LIVE_GATEWAY_DB", "")


def _rows(dump: str, table: str) -> list[str]:
    """The rows `pg_dump` wrote for `table` (between its COPY line and `\\.`)."""
    lines = dump.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith(f'COPY public."{table}"')), None)  # fmt: skip
    if start is None:
        return []
    rows = []
    for line in lines[start + 1 :]:
        if line == "\\.":
            break
        rows.append(line)
    return rows


@pytest.mark.skipif(not (PG_CONTAINER and GATEWAY_DB), reason="live: the gateway's Postgres")
async def test_the_real_pg_dump_leaves_out_every_sealed_row_of_the_real_gateway() -> None:
    """`05_DEPLOYMENT.md` §6.1 against the real thing: with the backup's own flags
    (`harness.backup._without_secrets`), the real `pg_dump` of the pinned gateway's database holds
    no row of a table that holds a key or a sealed value; without them, it does (the plant)."""
    import subprocess

    from harness.backup import GATEWAY_SEALED_TABLES, _without_secrets

    http = httpx.AsyncClient(base_url=URL, headers={"Authorization": f"Bearer {MASTER}"})
    gateway = GatewayAdmin(http)
    provider = ModelProviderConfig.model_construct(
        name="openai", label="Stand-in", roles={"extraction": "known-model"},
        api_base=PROVIDER_BASE, privacy_contract=False, contract_reference=None,
    )  # fmt: skip
    try:
        await gateway.put_credential("openai", SecretStr(GOOD))
        if entry_id("openai", "known-model") not in await gateway.stored_entries():
            await gateway.add_entry(provider, "known-model")

        def dump(*flags: str) -> str:
            argv = ["docker", "exec", PG_CONTAINER, "pg_dump", *flags, "-U", "osprey", GATEWAY_DB]
            return subprocess.run(argv, capture_output=True, text=True, check=True).stdout

        planted, kept = dump(), dump(*_without_secrets("litellm"))
        tables = [t.strip('"') for t in GATEWAY_SEALED_TABLES]
        assert _rows(planted, "LiteLLM_CredentialsTable") and _rows(planted, "LiteLLM_ProxyModelTable")
        assert all(_rows(kept, table) == [] for table in tables)
        assert GOOD not in kept
        assert 'CREATE TABLE public."LiteLLM_CredentialsTable"' in kept
    finally:
        await gateway.delete_credential("openai")
        await gateway.delete_entry(entry_id("openai", "known-model"))
        await http.aclose()
