"""Display names for principal ids, resolved at read time — `06_DECISIONS.md` ADR-106.

The id is identity; the name is presentation. Stores keep `principal.id` exactly as before, and a
read path that serves one for display asks this directory for its name while serving — **only for
ids already in that caller's authorised response** (decision 3: there is deliberately no lookup
route, which would let any caller resolve a UUID it was never served).

Names are read from the identity provider's admin users endpoint (`OIDC_ADMIN_USERS_URL/{id}`)
bearing the ADR-043 client-credentials token, the same view-users capability the revocation
pre-check holds. A name never gates anything, so unlike ADR-036's principals it may be cached: five
minutes per process (decision 4). A 404 — the id is not an account — is an answer and is cached
too; a transport failure is not, so one outage does not blank names for the TTL. An unknown id, an
unreachable identity provider or a deployment with no admin-users URL yields no name and **never a
failed read**: the caller shows the id, as before ADR-106.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

import httpx

from principal_auth import OidcSettings

#: ADR-106 decision 4.
NAME_TTL_SECONDS = 300.0


def _display_name(account: dict[str, object]) -> str | None:
    """"firstName lastName", or the username when the account carries neither name part."""
    parts = [str(account.get(key) or "").strip() for key in ("firstName", "lastName")]
    full = " ".join(part for part in parts if part)
    return full or str(account.get("username") or "").strip() or None


class PrincipalNameDirectory:
    """One per process, built at lifespan start beside the `PrincipalResolver`, closed with it."""

    def __init__(self, config: OidcSettings, *, ttl_seconds: float = NAME_TTL_SECONDS) -> None:
        self._config = config
        self._ttl = ttl_seconds
        self._http = httpx.AsyncClient(timeout=5.0)
        #: id -> (name or None for a known non-account, expiry). Transport failures are never
        #: written here.
        self._names: dict[str, tuple[str | None, float]] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    def _configured(self) -> bool:
        return bool(
            self._config.oidc_admin_users_url
            and self._config.oidc_token_exchange_url
            and self._config.oidc_token_exchange_client_id
        )

    async def _token(self) -> str:
        response = await self._http.post(
            self._config.oidc_token_exchange_url or "",
            data={
                "grant_type": "client_credentials",
                "client_id": self._config.oidc_token_exchange_client_id,
                "client_secret": self._config.oidc_token_exchange_client_secret,
            },
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    async def display_names(self, ids: Iterable[str]) -> dict[str, str]:
        """Names for the ids given, absent where there is none to give. The caller passes only
        ids its own authorised response already carries (ADR-106 decision 3)."""
        if not self._configured():
            return {}
        now = time.monotonic()
        resolved: dict[str, str] = {}
        to_fetch: list[str] = []
        for principal_id in dict.fromkeys(ids):
            if not principal_id:
                continue
            cached = self._names.get(principal_id)
            if cached is not None and cached[1] > now:
                if cached[0]:
                    resolved[principal_id] = cached[0]
            else:
                to_fetch.append(principal_id)
        if not to_fetch:
            return resolved
        try:
            token = await self._token()
        except httpx.HTTPError:
            return resolved
        for principal_id in to_fetch:
            try:
                response = await self._http.get(
                    f"{self._config.oidc_admin_users_url}/{principal_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError:
                continue
            if response.status_code == 200:
                name = _display_name(response.json())
                self._names[principal_id] = (name, now + self._ttl)
                if name:
                    resolved[principal_id] = name
            elif response.status_code == 404:
                self._names[principal_id] = (None, now + self._ttl)
        return resolved
