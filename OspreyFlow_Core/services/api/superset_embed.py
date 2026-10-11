"""Superset dashboards inside the Glass (`06_DECISIONS.md` ADR-111 Amendment 3).

The Conduit decides who may see an embedded dashboard; Superset only draws it. A Superset
dashboard is embeddable when its slug names a registered dashboard identity (`compliance-board` ↔
`osprey-dashboard-compliance-board`), and a person may open it only if they could see everything
that identity counts — its unit, a clearance at least its own, every handling code it receives,
and a level on every case it has been given (`may_open`). The guest token Superset issues is
read-only, short-lived and restricted to that identity's rows in the mart.

The Conduit talks to Superset as a local service user (`osprey-embedder`) whose password is a
deployment secret; Superset frames itself only for the Glass's origin.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from schemas.admin import DashboardIdentity
from schemas.domain import Principal

DASHBOARD_PREFIX = "osprey-dashboard-"
EMBEDDER = "osprey-embedder"


class SupersetRefused(Exception):
    """Superset refused the service user or the request; said in words."""


@dataclass(frozen=True)
class SupersetSettings:
    internal_url: str
    public_origin: str
    glass_origin: str
    password: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> SupersetSettings | None:
        """None when embedding is not configured — the Glass then lists no dashboards."""
        names = ("SUPERSET_INTERNAL_URL", "SUPERSET_PUBLIC_ORIGIN", "SUPERSET_GLASS_ORIGIN",
                 "SUPERSET_EMBEDDER_PASSWORD")  # fmt: skip
        values = [env.get(name, "") for name in names]
        return cls(*values) if all(values) else None


@dataclass(frozen=True)
class EmbeddableDashboard:
    slug: str
    title: str
    superset_id: int
    client_id: str


def identity_for(slug: str, identities: Sequence[DashboardIdentity]) -> DashboardIdentity | None:
    return next((d for d in identities if d.client_id == f"{DASHBOARD_PREFIX}{slug}"), None)


def identity_principal(identity: DashboardIdentity) -> Principal:
    """The dashboard identity as the Conduit sees it when it reads — for listing its cases."""
    return Principal(
        id=identity.account_id,
        clearance=identity.clearance or "",
        org_unit=identity.org_unit or "",
        receivable_handling_codes=list(identity.receivable_handling_codes),
        roles=["reports_viewer"],
    )


def may_open(
    viewer: Principal,
    identity: DashboardIdentity,
    *,
    classification: Sequence[str],
    viewer_cases: set[str],
    identity_cases: set[str],
) -> bool:
    """True only if the viewer could see everything the identity counts (Amendment 3, decision 2).
    An identity with an unknown clearance or unit is never opened."""
    if not identity.clearance or not identity.org_unit or identity.org_unit != viewer.org_unit:
        return False
    if identity.clearance not in classification or viewer.clearance not in classification:
        return False
    if classification.index(viewer.clearance) < classification.index(identity.clearance):
        return False
    if not set(identity.receivable_handling_codes) <= set(viewer.receivable_handling_codes):
        return False
    return identity_cases <= viewer_cases


class SupersetEmbedder:
    def __init__(
        self, settings: SupersetSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.internal_url, timeout=10.0, transport=transport
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _session(self) -> dict[str, str]:
        """Signs in as the service user; returns headers carrying its token and a CSRF token."""
        login = await self._http.post(
            "/api/v1/security/login",
            json={
                "username": EMBEDDER,
                "password": self.settings.password,
                "provider": "db",
                "refresh": False,
            },
        )
        if login.status_code != 200:
            raise SupersetRefused(f"Superset refused the service user ({login.status_code})")
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        csrf = await self._http.get("/api/v1/security/csrf_token/", headers=headers)
        if csrf.status_code != 200:
            raise SupersetRefused(f"Superset gave no CSRF token ({csrf.status_code})")
        return {
            **headers,
            "X-CSRFToken": str(csrf.json()["result"]),
            "Referer": self.settings.internal_url,
        }

    async def dashboards(self) -> list[tuple[int, str, str]]:
        """Every Superset dashboard with a slug: (id, slug, title)."""
        headers = await self._session()
        listed = await self._http.get(
            "/api/v1/dashboard/", params={"q": "(page_size:100)"}, headers=headers
        )
        if listed.status_code != 200:
            raise SupersetRefused(f"Superset refused the dashboard list ({listed.status_code})")
        return [(int(d["id"]), str(d["slug"]), str(d["dashboard_title"]))
                for d in listed.json().get("result", []) if d.get("slug")]  # fmt: skip

    async def embeddable(
        self, identities: Sequence[DashboardIdentity]
    ) -> list[EmbeddableDashboard]:
        return [
            EmbeddableDashboard(
                slug=slug, title=title, superset_id=sid, client_id=identity.client_id
            )
            for sid, slug, title in await self.dashboards()
            if (identity := identity_for(slug, identities)) is not None
        ]

    async def guest_token(
        self, dashboard: EmbeddableDashboard, viewer: Principal, name: str
    ) -> tuple[str, str]:
        """(token, embedded uuid) for one dashboard, its rows limited to the identity's own."""
        headers = await self._session()
        uuid = await self._embedded_uuid(dashboard.superset_id, headers)
        quoted = dashboard.client_id.replace("'", "''")
        body: dict[str, Any] = {
            "user": {"username": viewer.id, "first_name": name or viewer.id, "last_name": ""},
            "resources": [{"type": "dashboard", "id": uuid}],
            "rls": [{"clause": f"dashboard = '{quoted}'"}],
        }
        granted = await self._http.post("/api/v1/security/guest_token/", json=body, headers=headers)
        if granted.status_code != 200:
            raise SupersetRefused(f"Superset refused a guest token ({granted.status_code})")
        return str(granted.json()["token"]), uuid

    async def _embedded_uuid(self, superset_id: int, headers: dict[str, str]) -> str:
        """The dashboard's embedded configuration for the Glass's origin, made the first time."""
        path = f"/api/v1/dashboard/{superset_id}/embedded"
        found = await self._http.get(path, headers=headers)
        allowed = [self.settings.glass_origin]
        if found.status_code == 200 and found.json()["result"].get("allowed_domains") == allowed:
            return str(found.json()["result"]["uuid"])
        made = await self._http.post(path, json={"allowed_domains": allowed}, headers=headers)
        if made.status_code != 200:
            raise SupersetRefused(
                f"Superset would not embed dashboard {superset_id} ({made.status_code})"
            )
        return str(made.json()["result"]["uuid"])
