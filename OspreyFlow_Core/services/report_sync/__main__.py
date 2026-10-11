"""`python -m services.report_sync` — the report sync service (`06_DECISIONS.md` ADR-111
Amendment 2), a deployment component of its own.

Configuration, all from the environment (the deployment's env file — secrets never in the mart):

- `REPORT_SYNC_DASHBOARDS` — a JSON list of `{"client_id", "secret", "weeks"?}`, each a dashboard
  identity registered in the Admin area (its secret is shown there once);
- `REPORT_SYNC_TOKEN_URL` — the identity provider's token endpoint;
- `REPORT_SYNC_CONDUIT_URL` — where the Conduit answers (inside the deployment's network);
- `REPORT_SYNC_INTERVAL_SECONDS` — how often each case is pulled (900 by default);
- `REPORT_MART_READER` / `REPORT_MART_READER_PASSWORD` — the login a BI tool reads the mart as;
- the usual `POSTGRES_*` and `VALKEY_*`.

Each pass claims its slot (`time // interval`), so any number of instances pull each case once.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Mapping

from services.api.config import PostgresConfig, ValkeyConfig
from valkey.asyncio import Valkey

from .mart import Mart
from .sync import Dashboard, sync_once

log = logging.getLogger("report_sync")


def dashboards_from_env(env: Mapping[str, str]) -> list[Dashboard]:
    """The configured dashboards, refused in words when the configuration is not usable."""
    token_url = env.get("REPORT_SYNC_TOKEN_URL", "")
    conduit_url = env.get("REPORT_SYNC_CONDUIT_URL", "")
    if not token_url or not conduit_url:
        raise SystemExit("REPORT_SYNC_TOKEN_URL and REPORT_SYNC_CONDUIT_URL must both be set")
    try:
        listed = json.loads(env.get("REPORT_SYNC_DASHBOARDS", "[]"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"REPORT_SYNC_DASHBOARDS is not JSON: {e}") from e
    boards = []
    for entry in listed:
        client_id, secret = str(entry.get("client_id", "")), str(entry.get("secret", ""))
        if not client_id.startswith("osprey-dashboard-") or not secret:
            raise SystemExit(
                f"a dashboard needs an osprey-dashboard-* client_id and a secret: {client_id!r}"
            )
        boards.append(
            Dashboard(client_id=client_id, secret=secret, token_url=token_url,
                      conduit_url=conduit_url, weeks=int(entry.get("weeks", 12)))
        )  # fmt: skip
    return boards


async def run(env: Mapping[str, str]) -> None:
    boards = dashboards_from_env(env)
    interval = max(60, int(env.get("REPORT_SYNC_INTERVAL_SECONDS", "900")))
    mart = await Mart.connect(PostgresConfig.from_env().dsn)
    reader, password = (
        env.get("REPORT_MART_READER", "osprey_reports_reader"),
        env.get("REPORT_MART_READER_PASSWORD"),
    )
    if password:
        await mart.ensure_reader(reader, password)
    cfg = ValkeyConfig.from_env()
    valkey = Valkey(host=cfg.host, port=cfg.port, db=cfg.db)
    log.info("report-sync: %d dashboard(s), every %d s", len(boards), interval)
    try:
        while True:
            slot = int(time.time() // interval)
            summary = await sync_once(boards, mart, valkey, slot=slot)
            log.info(
                "report-sync slot %d: %d pulled, %d skipped, %d failed, %d figure(s) changed",
                slot, summary.pulled, summary.skipped, summary.failed, summary.changed,
            )  # fmt: skip
            for failure in summary.failures:
                log.warning("report-sync: %s", failure)
            await asyncio.sleep(max(1.0, (slot + 1) * interval - time.time()))
    finally:
        await mart.close()
        await valkey.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(os.environ))
