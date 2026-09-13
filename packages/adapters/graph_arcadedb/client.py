"""Thin async HTTP client over ArcadeDB's REST API.

ArcadeDB's TinkerPop bridge is reached through its `/api/v1/command`
endpoint with `language: gremlin` — this container does not run a separate
Gremlin Server/WebSocket listener by default, so this is the actual
transport `local-lite`'s single ArcadeDB container offers. The Gremlin
*content* still never leaves the Vault: the Conduit only ever calls typed
`GraphPort` methods, and the traversal strings are built and sent
server-side, by this adapter, from the bounded builders in `builders.py`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx


class ArcadeDBError(Exception):
    """An ArcadeDB command failed — surfaced with the server's own message."""


@dataclass(frozen=True, slots=True)
class ArcadeDBConfig:
    host: str = "localhost"
    http_port: int = 2480
    username: str = "root"
    password: str = "playwithdata123"
    database: str = "mantisnexus"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.http_port}"

    @classmethod
    def from_env(cls, database: str) -> ArcadeDBConfig:
        """CI and local `docker run` both read connection info from the
        environment — see the `conformance` job in `.github/workflows/ci.yml`."""
        return cls(
            host=os.environ.get("ARCADEDB_HOST", "localhost"),
            http_port=int(os.environ.get("ARCADEDB_HTTP_PORT", "2480")),
            username=os.environ.get("ARCADEDB_USERNAME", "root"),
            password=os.environ.get("ARCADEDB_ROOT_PASSWORD", "playwithdata123"),
            database=database,
        )


class ArcadeDBClient:
    def __init__(self, config: ArcadeDBConfig) -> None:
        self._config = config
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            auth=(config.username, config.password),
            timeout=30.0,
        )

    @property
    def database(self) -> str:
        return self._config.database

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- server / database lifecycle ------------------------------------

    async def create_database_if_absent(self) -> None:
        databases = await self._server_command("list databases")
        if self._config.database not in databases:
            await self._server_command(f"create database {self._config.database}")

    async def drop_database(self) -> None:
        databases = await self._server_command("list databases")
        if self._config.database in databases:
            await self._server_command(f"drop database {self._config.database}")

    async def _server_command(self, command: str) -> Any:
        resp = await self._http.post("/api/v1/server", json={"command": command})
        self._raise_for_error(resp)
        return resp.json().get("result")

    # --- transactions ------------------------------------------------------

    async def begin_transaction(self) -> str:
        resp = await self._http.post(f"/api/v1/begin/{self._config.database}")
        self._raise_for_error(resp)
        session_id = resp.headers.get("arcadedb-session-id")
        if not session_id:
            raise ArcadeDBError("ArcadeDB did not return a session id for the new transaction")
        return str(session_id)

    async def commit_transaction(self, session_id: str) -> None:
        resp = await self._http.post(
            f"/api/v1/commit/{self._config.database}",
            headers={"arcadedb-session-id": session_id},
        )
        self._raise_for_error(resp)

    async def rollback_transaction(self, session_id: str) -> None:
        resp = await self._http.post(
            f"/api/v1/rollback/{self._config.database}",
            headers={"arcadedb-session-id": session_id},
        )
        self._raise_for_error(resp)

    # --- commands ------------------------------------------------------

    async def sql(
        self,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.command("sql", command, params=params, session_id=session_id)

    async def gremlin(
        self,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.command("gremlin", command, params=params, session_id=session_id)

    async def command(
        self,
        language: str,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"language": language, "command": command}
        if params:
            body["params"] = dict(params)
        headers = {"arcadedb-session-id": session_id} if session_id else None
        resp = await self._http.post(
            f"/api/v1/command/{self._config.database}", json=body, headers=headers
        )
        self._raise_for_error(resp)
        result = resp.json().get("result", [])
        if not isinstance(result, list):
            raise ArcadeDBError(f"unexpected ArcadeDB response shape: {result!r}")
        return result

    @staticmethod
    def _raise_for_error(resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise ArcadeDBError(f"ArcadeDB error {resp.status_code}: {resp.text}")
