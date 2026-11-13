"""The Admin area's calls to the identity provider (`06_DECISIONS.md` ADR-112 Amendment 1): people's
roles, and dashboard identities (ADR-111 decision 7).

**Through the Conduit's own service account,** bearing the ADR-043 client-credentials token, so
every change passes the Conduit's right check and audit; the account needs `manage-users` and
`manage-clients`. **Narrowed here, before any call:** a person's `roles` attribute may hold only the
built-in roles, custom roles (`role:<id>`, ADR-145 Amendment 5), single `right:<name>` grants
and the old role names — nothing else, so this can never hand out realm administration — and only
a client named `osprey-dashboard-*` is ever created or removed.

**A dashboard identity** is a confidential client with a service account and no browser flow: its
token carries the principal claims (clearance, unit, roles — `reports_viewer` — handling codes) from
the service account's attributes, and the Conduit's audience. Its secret is handed over once, at
registration, and never stored by OspreyFlow. Case access is ADR-052's: a case Author grants the
identity's account Viewer, as for a person.
"""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx

from principal_auth import OidcSettings
from schemas.admin import (
    AccessInput,
    DashboardIdentity,
    InviteInput,
    OrganisationArrival,
    PersonAccount,
    RegisteredDashboard,
    SignInDelivery,
)
from schemas.rights import (
    CUSTOM_ROLE_PREFIX,
    LEGACY_ROLE_RIGHTS,
    ROLE_RIGHTS,
    SINGLE_RIGHT_PREFIX,
    Right,
    rights_for,
)

DASHBOARD_PREFIX = "osprey-dashboard-"
_RIGHT_VALUES = {r.value for r in Right}
#: The claims a principal is built from (`harness/realm.py::PRINCIPAL_CLAIMS`), mapped from user
#: attributes; kept in step with it by `test_identity_admin.py`'s mapper case.
_PRINCIPAL_CLAIMS = (("clearance", False), ("org_unit", False),
                     ("receivable_handling_codes", True), ("roles", True))  # fmt: skip


#: Accounts OspreyFlow itself uses that are not a client's service account: the deploy's verify
#: probes (`harness/realm.py`'s `VERIFY_SUBJECT` and `REVOKED_SUBJECT`, held equal by
#: `test_identity_admin.py`). Never removed and never joined to an organisation account (ADR-112
#: Amendment 3); a client's service account (`service-account-*`) is no person at all.
CONDUIT_ACCOUNTS = frozenset({"osprey-verify-probe", "osprey-verify-revoked"})

#: ADR-112 Amendment 3 (b): Keycloak's record of a refused first sign-in through the organisation
#: (`harness/realm.py`'s `ARRIVAL_EVENT`, held equal by a test). Its `identity_provider_identity`
#: is "<preferred_username> <sub>" — the username-template mapper the provider carries
#: (`harness/realm.py`'s `organisation_provider_mappers`); measured on Keycloak 26.0, the record
#: holds no other id for the person.
ARRIVAL_EVENT = "IDENTITY_PROVIDER_FIRST_LOGIN_ERROR"


#: The identity provider's page of people; `list_people` reads every page.
_PAGE = 500


class IdentityAdminRefused(Exception):
    """The identity provider refused or could not be reached; said in words, never swallowed."""


class PersonActionRefused(Exception):
    """An Admin -> People action OspreyFlow refuses, before the identity provider is changed
    (ADR-112 Amendment 3): `error` is the answer's code, `words` what the administrator reads."""

    def __init__(self, error: str, words: str) -> None:
        super().__init__(words)
        self.error = error
        self.words = words


class ConduitCredentialRefused(IdentityAdminRefused):
    """The identity provider answered and refused the Conduit's own client credential (ADR-114
    Amendment 36): after a wipe or a re-import the realm holds a secret Keycloak made (step 18a's
    D2), and the Conduit can act for nobody until `ospreyflow repair-sign-in` sets it again."""


#: How long Admin -> System keeps the answer to "can the Conduit act for people?" (ADR-114
#: Amendment 36): one token request per half minute at most, however often the screen is asked.
CREDENTIAL_CHECK_SECONDS = 30.0


@dataclass(frozen=True)
class CredentialCheck:
    """Whether the identity provider grants the Conduit's own client credential: `accepted`,
    `refused` (it answered no) or `unreachable` (it did not answer). `detail` is in words and never
    carries the secret or the identity provider's answer."""

    state: Literal["accepted", "refused", "unreachable"]
    millis: int
    detail: str | None


class UnknownRoleError(ValueError):
    """A role outside the known set, or a client that is not a dashboard's — refused before any
    call to the identity provider."""


class DashboardExistsError(Exception):
    pass


class PersonExistsError(Exception):
    """The sign-in name or the email address is already held (the identity provider's 409)."""


#: The one-time code's letters: no 0/O or 1/I, so it can be read out and typed without a slip.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def one_time_code() -> str:
    """Sixteen letters in four groups — 80 bits. Keycloak applies no password policy of its own
    (measured: a one-letter password was accepted), so the strength is this code's."""
    letters = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    return "-".join(letters[i : i + 4] for i in range(0, 16, 4))


#: A custom role's id (`custom_roles.py`, `secrets.token_hex(6)`): whether it exists is the
#: route's to check, against the store.
_CUSTOM_ROLE = re.compile(rf"^{re.escape(CUSTOM_ROLE_PREFIX)}[a-z0-9]{{1,32}}$")


def allowed_role(role: str) -> bool:
    if role in ROLE_RIGHTS or role in LEGACY_ROLE_RIGHTS:
        return True
    if _CUSTOM_ROLE.match(role):
        return True
    return (
        role.startswith(SINGLE_RIGHT_PREFIX) and role[len(SINGLE_RIGHT_PREFIX) :] in _RIGHT_VALUES
    )


def _first(attributes: dict[str, Any], key: str) -> str | None:
    values = attributes.get(key) or []
    return str(values[0]) if values else None


def _arrival_identity(raw: object) -> tuple[str, str] | None:
    """(provider username, subject) from a refusal's `identity_provider_identity`, or None for one
    recorded before the provider carried the mapper (it holds the username alone)."""
    if not isinstance(raw, str) or " " not in raw.strip():
        return None
    username, _, subject = raw.strip().rpartition(" ")
    return (username.strip(), subject) if subject else None


def _system(user: dict[str, Any]) -> bool:
    """An account OspreyFlow itself uses: a client's service account, or a `CONDUIT_ACCOUNTS`."""
    username = str(user.get("username", ""))
    return (
        username.startswith("service-account-")
        or bool(user.get("serviceAccountClientId"))
        or username in CONDUIT_ACCOUNTS
    )


def _person(user: dict[str, Any]) -> PersonAccount:
    attributes = user.get("attributes") or {}
    name = " ".join(str(user.get(k) or "").strip() for k in ("firstName", "lastName")).strip()
    return PersonAccount(
        id=str(user["id"]),
        username=str(user.get("username", "")),
        name=name or str(user.get("username", "")),
        enabled=bool(user.get("enabled", True)),
        roles=[str(r) for r in attributes.get("roles") or []],
        clearance=_first(attributes, "clearance"),
        org_unit=_first(attributes, "org_unit"),
        email=user.get("email") or None,
        receivable_handling_codes=[
            str(c) for c in attributes.get("receivable_handling_codes") or []
        ],
        must_set_password="UPDATE_PASSWORD" in (user.get("requiredActions") or []),
        system_account=_system(user),
    )


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise UnknownRoleError("a dashboard needs a name of letters or digits")
    return slug[:48]


class PeopleDirectory(Protocol):
    """What Admin › People's routes call: `IdentityAdmin` on Keycloak, and
    `entra_people.EntraPeopleAdmin` on Entra ID sign-in (ADR-148 Amendment 8), which refuses in
    words what Entra holds."""

    async def aclose(self) -> None: ...
    async def reachable(self) -> None: ...
    async def credential_check(self) -> CredentialCheck: ...
    async def list_people(self) -> list[PersonAccount]: ...
    async def set_roles(self, user_id: str, roles: list[str]) -> PersonAccount: ...
    async def invite(self, invite: InviteInput) -> SignInDelivery: ...
    async def set_access(self, user_id: str, access: AccessInput) -> PersonAccount: ...
    async def set_enabled(self, user_id: str, enabled: bool) -> PersonAccount: ...
    async def reset_sign_in(self, user_id: str) -> SignInDelivery: ...
    async def remove_person(
        self, user_id: str, custom: Mapping[str, Iterable[Right]] | None = None
    ) -> PersonAccount: ...
    async def list_arrivals(self) -> list[OrganisationArrival]: ...
    async def link_organisation(
        self, user_id: str, subject: str
    ) -> tuple[PersonAccount, OrganisationArrival]: ...
    async def list_dashboards(self) -> list[DashboardIdentity]: ...
    async def create_dashboard(
        self, name: str, *, clearance: str, org_unit: str, application_id: str | None = None
    ) -> RegisteredDashboard: ...
    async def delete_dashboard(self, client_id: str) -> None: ...


class IdentityAdmin:
    """One per process, beside the `PrincipalResolver`; closed with it."""

    def __init__(
        self, settings: OidcSettings, *, by_email: bool = False, organisation: str | None = None
    ) -> None:
        self._settings = settings
        #: ADR-112 Amendment 3 (b): the organisation's sign-in alias
        #: (`OSPREY_ORGANISATION_SIGN_IN`), or None with no sign-in through an organisation.
        self._organisation = organisation or None
        self._http = httpx.AsyncClient(timeout=10.0)
        #: ADR-114 Amendment 5: the deployment has a mail server, so a person with an address is
        #: signed in by the identity provider's own emailed link; anyone else by a one-time code.
        self._by_email = by_email
        self._clock: Callable[[], float] = time.monotonic
        self._credential: tuple[float, CredentialCheck] | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def _realm(self) -> str:
        users = self._settings.oidc_admin_users_url or ""
        if not users.endswith("/users"):
            raise IdentityAdminRefused("this deployment has no identity-provider admin address")
        return users[: -len("/users")]

    async def _token(self) -> str:
        try:
            response = await self._http.post(
                self._settings.oidc_token_exchange_url or "",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._settings.oidc_token_exchange_client_id,
                    "client_secret": self._settings.oidc_token_exchange_client_secret,
                },
            )
        except httpx.HTTPError as e:
            raise IdentityAdminRefused(f"the identity provider could not be reached: {e}") from e
        if response.status_code in (400, 401):
            # Keycloak 26: 401 `unauthorized_client` for a client it holds with another secret, 401
            # `invalid_client` for one it does not hold. Its answer is not repeated.
            raise ConduitCredentialRefused(
                "the identity provider refused the Conduit's credentials"
            )
        if response.status_code != 200:
            raise IdentityAdminRefused(
                f"the identity provider did not answer the Conduit ({response.status_code})"
            )
        return str(response.json()["access_token"])

    async def _call(
        self, method: str, path: str, *, json: Any = None, params: Any = None
    ) -> httpx.Response:
        token = await self._token()
        try:
            response = await self._http.request(
                method, f"{self._realm}{path}", json=json, params=params,
                headers={"Authorization": f"Bearer {token}"},
            )  # fmt: skip
        except httpx.HTTPError as e:
            raise IdentityAdminRefused(f"the identity provider could not be reached: {e}") from e
        if response.status_code in (401, 403):
            raise IdentityAdminRefused(
                "the identity provider refused the Conduit — its account needs manage-users, "
                "manage-clients and view-events: run ospreyflow repair-sign-in"
            )
        return response

    async def reachable(self) -> None:
        """Raises `IdentityAdminRefused` unless the identity provider grants the Conduit a token."""
        await self._token()

    async def credential_check(self) -> CredentialCheck:
        """Can the Conduit act for people? (ADR-114 Amendment 36, Admin -> System.) One
        client-credentials request, its answer kept for `CREDENTIAL_CHECK_SECONDS`."""
        now = self._clock()
        if self._credential is not None and now - self._credential[0] < CREDENTIAL_CHECK_SECONDS:
            return self._credential[1]
        started = time.monotonic()
        state: Literal["accepted", "refused", "unreachable"]
        try:
            await self._token()
            state, detail = "accepted", None
        except ConduitCredentialRefused:
            state, detail = "refused", "the identity provider refused the Conduit's credentials"
        except IdentityAdminRefused:
            state, detail = "unreachable", "the identity provider did not answer"
        check = CredentialCheck(state, int((time.monotonic() - started) * 1000), detail)
        self._credential = (now, check)
        return check

    # --- people -------------------------------------------------------------------------------

    async def list_people(self) -> list[PersonAccount]:
        # Paged to the end, never cut at a page (rule 2): the lock-out and a team's members read
        # this list whole.
        users: list[dict[str, Any]] = []
        while True:
            response = await self._call(
                "GET",
                "/users",
                params={"first": len(users), "max": _PAGE, "briefRepresentation": "false"},
            )
            if response.status_code != 200:
                raise IdentityAdminRefused(
                    f"the identity provider did not list the people ({response.status_code})"
                )
            page = response.json()
            users += page
            if len(page) < _PAGE:
                break
        linked = await self._linked_ids()
        people = [
            _person(u).model_copy(update={"organisation_linked": str(u.get("id")) in linked})
            for u in users
            if not str(u.get("username", "")).startswith("service-account-")
        ]
        return sorted(people, key=lambda p: p.username)

    async def _linked_ids(self, subject: str | None = None) -> set[str]:
        """The accounts joined to the organisation's provider — or, given `subject`, the one joined
        to that organisation account. Empty without an organisation."""
        if not self._organisation:
            return set()
        params: dict[str, Any] = {"idpAlias": self._organisation, "max": 500}
        if subject is not None:
            params["idpUserId"] = subject
        found = await self._call("GET", "/users", params=params)
        if found.status_code != 200:
            raise IdentityAdminRefused(
                f"the identity provider did not say who is joined ({found.status_code})"
            )
        return {str(u["id"]) for u in found.json()}

    async def set_roles(self, user_id: str, roles: list[str]) -> PersonAccount:
        refused = [r for r in roles if not allowed_role(r)]
        if refused:
            raise UnknownRoleError(
                f"not a role or right this deployment grants: {', '.join(refused)}"
            )
        found = await self._call("GET", f"/users/{user_id}")
        if found.status_code == 404:
            raise IdentityAdminRefused("no such person")
        user = found.json()
        attributes = {**(user.get("attributes") or {}), "roles": list(dict.fromkeys(roles))}
        written = await self._call(
            "PUT", f"/users/{user_id}", json={**user, "attributes": attributes}
        )
        if written.status_code not in (200, 204):
            raise IdentityAdminRefused(
                f"the identity provider did not save the roles ({written.status_code})"
            )
        return _person({**user, "attributes": attributes})

    # --- invite, access, disable, enable, reset sign-in (ADR-114 Amendment 5) ------------------

    async def _user(self, user_id: str) -> dict[str, Any]:
        found = await self._call("GET", f"/users/{user_id}")
        user = found.json() if found.status_code == 200 else None
        if not user or str(user.get("username", "")).startswith("service-account-"):
            raise IdentityAdminRefused("no such person")
        return dict(user)

    def _emailed(self, email: str | None) -> bool:
        return self._by_email and bool(email)

    async def _put_user(self, user: dict[str, Any], what: str) -> None:
        # Measured: a PUT replaces each key it names — `attributes` whole — so the person is always
        # written back entire, read first.
        written = await self._call("PUT", f"/users/{user['id']}", json=user)
        if written.status_code not in (200, 204):
            raise IdentityAdminRefused(
                f"the identity provider did not save the {what} ({written.status_code})"
            )

    async def _send_set_password_email(self, user_id: str) -> None:
        sent = await self._call(
            "PUT", f"/users/{user_id}/execute-actions-email", json=["UPDATE_PASSWORD"]
        )
        if sent.status_code not in (200, 204):
            detail = sent.json().get("errorMessage", "") if sent.content else ""
            said = f"the sign-in email could not be sent: {detail}"
            raise IdentityAdminRefused(said.rstrip(": "))

    async def invite(self, invite: InviteInput) -> SignInDelivery:
        refused = [r for r in invite.roles if not allowed_role(r)]
        if refused:
            raise UnknownRoleError(
                f"not a role or right this deployment grants: {', '.join(refused)}"
            )
        attributes = {
            "clearance": [invite.clearance],
            "org_unit": [invite.org_unit],
            "receivable_handling_codes": list(dict.fromkeys(invite.receivable_handling_codes)),
            "roles": list(dict.fromkeys(invite.roles)),
        }
        user: dict[str, Any] = {
            "username": invite.username,
            "firstName": invite.first_name,
            "lastName": invite.last_name,
            "enabled": True,
            "emailVerified": False,
            "attributes": attributes,
            "requiredActions": ["UPDATE_PASSWORD"],
        }
        if invite.email:
            user["email"] = invite.email
        emailed = self._emailed(invite.email)
        code = None if emailed else one_time_code()
        if code is not None:
            user["credentials"] = [{"type": "password", "value": code, "temporary": True}]
        created = await self._call("POST", "/users", json=user)
        if created.status_code == 409:
            raise PersonExistsError(invite.username)
        if created.status_code == 400:
            raise UnknownRoleError(f"the identity provider refused the person: {created.text}")
        if created.status_code != 201:
            raise IdentityAdminRefused(
                f"the identity provider did not create the person ({created.status_code})"
            )
        user_id = created.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]
        if emailed:
            try:
                await self._send_set_password_email(user_id)
            except IdentityAdminRefused:
                # No half-made account: the administrator can invite again once mail works.
                await self._call("DELETE", f"/users/{user_id}")
                raise
        user.pop("credentials", None)
        person = _person({**user, "id": user_id})
        return SignInDelivery(
            person=person, delivery="email" if emailed else "one_time_code", one_time_code=code
        )

    async def set_access(self, user_id: str, access: AccessInput) -> PersonAccount:
        user = await self._user(user_id)
        attributes = {
            **(user.get("attributes") or {}),
            "clearance": [access.clearance],
            "org_unit": [access.org_unit],
            "receivable_handling_codes": list(dict.fromkeys(access.receivable_handling_codes)),
        }
        user = {**user, "attributes": attributes}
        await self._put_user(user, "access")
        return _person(user)

    async def set_enabled(self, user_id: str, enabled: bool) -> PersonAccount:
        user = {**await self._user(user_id), "enabled": enabled}
        await self._put_user(user, "account")
        if not enabled:
            # Sessions already open end now, not when their tokens lapse.
            await self._call("POST", f"/users/{user_id}/logout")
        return _person(user)

    async def reset_sign_in(self, user_id: str) -> SignInDelivery:
        user = await self._user(user_id)
        actions = list(dict.fromkeys([*(user.get("requiredActions") or []), "UPDATE_PASSWORD"]))
        user = {**user, "requiredActions": actions}
        emailed = self._emailed(user.get("email"))
        code = None if emailed else one_time_code()
        if code is not None:
            reset = await self._call(
                "PUT", f"/users/{user_id}/reset-password",
                json={"type": "password", "value": code, "temporary": True},
            )  # fmt: skip
            if reset.status_code not in (200, 204):
                raise IdentityAdminRefused(
                    f"the identity provider did not reset the sign-in ({reset.status_code})"
                )
        await self._put_user(user, "sign-in")
        if emailed:
            await self._send_set_password_email(user_id)
        await self._call("POST", f"/users/{user_id}/logout")
        return SignInDelivery(
            person=_person(user), delivery="email" if emailed else "one_time_code",
            one_time_code=code,
        )  # fmt: skip

    # --- remove (ADR-112 Amendment 3) ----------------------------------------------------------

    async def remove_person(
        self, user_id: str, custom: Mapping[str, Iterable[Right]] | None = None
    ) -> PersonAccount:
        """The person's account deleted from the identity provider: they can no longer sign in, and
        their sign-in name and email address are free again. Nothing OspreyFlow stores is changed —
        what they made keeps their id (ADR-106 shows it in place of a name). Refused, before
        anything is changed: an account OspreyFlow itself uses, and the last enabled person who
        can manage people. Returns the person as they were, for the audit record."""
        found = await self._call("GET", f"/users/{user_id}")
        user = found.json() if found.status_code == 200 else None
        if not user:
            raise IdentityAdminRefused("no such person")
        person = _person(user)
        if _system(user):
            raise PersonActionRefused(
                "not_a_person",
                f"{person.username} is an account OspreyFlow itself uses, not a person's; it "
                "cannot be removed.",
            )
        if person.enabled and Right.MANAGE_PEOPLE in rights_for(person.roles, custom):
            # Every page, and a custom role by its current rights (ADR-145 Amendment 5).
            others = [
                p for p in await self.list_people()
                if p.id != user_id and not p.system_account and p.enabled
                and Right.MANAGE_PEOPLE in rights_for(p.roles, custom)
            ]  # fmt: skip
            if not others:
                raise PersonActionRefused(
                    "last_administrator",
                    f"{person.username} is the only enabled person who can manage people. Give "
                    "someone else the Admin role first, so the deployment is not left with no "
                    "administrator.",
                )
        gone = await self._call("DELETE", f"/users/{user_id}")
        if gone.status_code == 404:
            raise IdentityAdminRefused("no such person")
        if gone.status_code not in (200, 204):
            raise IdentityAdminRefused(
                f"the identity provider did not remove the person ({gone.status_code})"
            )
        return person

    # --- join an organisation account (ADR-112 Amendment 3 (b)) --------------------------------

    async def list_arrivals(self) -> list[OrganisationArrival]:
        """Everyone the organisation's sign-in refused for a held email address (step 28 (e)), from
        Keycloak's own record of each refusal (kept seven days), newest first — one line a person,
        and none for a person since joined to an account. Empty without an organisation."""
        if not self._organisation:
            return []
        found = await self._call("GET", "/events", params={"type": ARRIVAL_EVENT, "max": 500})
        if found.status_code != 200:
            raise IdentityAdminRefused(
                f"the identity provider did not give its record of refused sign-ins "
                f"({found.status_code})"
            )
        arrivals: dict[str, OrganisationArrival] = {}
        for event in found.json():
            details = event.get("details") or {}
            if (
                event.get("type") != ARRIVAL_EVENT
                or event.get("error") != "access_denied"
                or details.get("identity_provider") != self._organisation
            ):
                continue
            parsed = _arrival_identity(details.get("identity_provider_identity"))
            if parsed is None:
                continue
            username, subject = parsed
            when = datetime.fromtimestamp(int(event.get("time", 0)) / 1000, UTC)
            held = arrivals.get(subject)
            arrivals[subject] = (
                OrganisationArrival(
                    subject=subject, provider_username=username, last_refused=when, attempts=1
                )
                if held is None
                else held.model_copy(
                    update={"attempts": held.attempts + 1,
                            "last_refused": max(held.last_refused, when)}
                )
            )  # fmt: skip
        waiting = [a for s, a in arrivals.items() if not await self._linked_ids(s)]
        return sorted(waiting, key=lambda a: a.last_refused, reverse=True)

    async def link_organisation(
        self, user_id: str, subject: str
    ) -> tuple[PersonAccount, OrganisationArrival]:
        """The refused arrival `subject` joined to the account `user_id` — Keycloak's own federated
        identity link, made with the organisation's id for them — so their next sign-in through the
        organisation lands in this account, with its roles. Refused, before anything changes: no
        organisation; an account OspreyFlow itself uses; an account already joined to an
        organisation account; and an id that is no refused arrival waiting to be joined (Keycloak
        itself would join one organisation account to two people, and to a service account —
        measured on 26.0). An invited account whose password was never set loses its one-time code:
        it is reached through the organisation from now on."""
        alias = self._organisation
        if not alias:
            raise PersonActionRefused(
                "no_organisation_sign_in",
                "This deployment has no sign-in through an organisation, so there is no "
                "organisation account to join.",
            )
        found = await self._call("GET", f"/users/{user_id}")
        user = found.json() if found.status_code == 200 else None
        if not user:
            raise IdentityAdminRefused("no such person")
        person = _person(user)
        if _system(user):
            raise PersonActionRefused(
                "not_a_person",
                f"{person.username} is an account OspreyFlow itself uses, not a person's; it "
                "cannot be joined to an organisation account.",
            )
        links = await self._call("GET", f"/users/{user_id}/federated-identity")
        if any(link.get("identityProvider") == alias for link in links.json() or []):
            raise PersonActionRefused(
                "already_linked",
                f"{person.username} is already joined to an organisation account. One OspreyFlow "
                "account is joined to one organisation account.",
            )
        arrival = next((a for a in await self.list_arrivals() if a.subject == subject), None)
        if arrival is None:
            raise PersonActionRefused(
                "no_such_arrival",
                "No refused organisation sign-in with that id is waiting to be joined: it may "
                "already be joined to an account. Ask the person to sign in through the "
                "organisation once more, then look again.",
            )
        made = await self._call(
            "POST", f"/users/{user_id}/federated-identity/{alias}",
            json={"identityProvider": alias, "userId": subject,
                  "userName": f"{arrival.provider_username} {subject}"},
        )  # fmt: skip
        if made.status_code == 409:
            raise PersonActionRefused(
                "already_linked", f"{person.username} is already joined to an organisation account."
            )
        if made.status_code not in (200, 201, 204):
            raise IdentityAdminRefused(
                f"the identity provider did not join the accounts ({made.status_code})"
            )
        actions = list(user.get("requiredActions") or [])
        if "UPDATE_PASSWORD" in actions:
            # Invited or reset and never signed in: the one-time code is withdrawn, and the person
            # is not asked to set a password they will not use (measured on 26.0: the pending
            # action stops the organisation sign-in at "Update password").
            held = await self._call("GET", f"/users/{user_id}/credentials")
            for credential in held.json() if held.status_code == 200 else []:
                if credential.get("type") == "password":
                    await self._call("DELETE", f"/users/{user_id}/credentials/{credential['id']}")
            user = {**user, "requiredActions": [a for a in actions if a != "UPDATE_PASSWORD"]}
            await self._put_user(user, "account")
        joined = _person(user).model_copy(update={"organisation_linked": True})
        return joined, arrival

    # --- dashboards ---------------------------------------------------------------------------

    def _client(self, client_id: str, audience: str) -> dict[str, Any]:
        mappers = [
            {
                "name": claim, "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "config": {"user.attribute": claim, "claim.name": claim, "jsonType.label": "String",
                           "multivalued": "true" if many else "false",
                           "access.token.claim": "true", "id.token.claim": "false"},
            }
            for claim, many in _PRINCIPAL_CLAIMS
        ] + [{
            "name": "audience-conduit", "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {"included.custom.audience": audience, "access.token.claim": "true",
                       "id.token.claim": "false"},
        }]  # fmt: skip
        return {
            "clientId": client_id, "protocol": "openid-connect", "publicClient": False,
            "serviceAccountsEnabled": True, "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False, "implicitFlowEnabled": False,
            "protocolMappers": mappers,
        }  # fmt: skip

    async def _uuid(self, client_id: str) -> str | None:
        found = (await self._call("GET", "/clients", params={"clientId": client_id})).json()
        exact = [c for c in found if c.get("clientId") == client_id]
        return str(exact[0]["id"]) if exact else None

    async def _identity(self, client: dict[str, Any]) -> DashboardIdentity:
        account = (await self._call("GET", f"/clients/{client['id']}/service-account-user")).json()
        attributes = account.get("attributes") or {}
        return DashboardIdentity(
            client_id=str(client["clientId"]), account_id=str(account["id"]),
            clearance=_first(attributes, "clearance"), org_unit=_first(attributes, "org_unit"),
            receivable_handling_codes=[
                str(c) for c in attributes.get("receivable_handling_codes") or []
            ],
        )  # fmt: skip

    async def list_dashboards(self) -> list[DashboardIdentity]:
        found = (
            await self._call(
                "GET", "/clients", params={"clientId": DASHBOARD_PREFIX, "search": "true"}
            )
        ).json()
        return [
            await self._identity(c)
            for c in found
            if str(c.get("clientId", "")).startswith(DASHBOARD_PREFIX)
        ]

    async def create_dashboard(
        self, name: str, *, clearance: str, org_unit: str, application_id: str | None = None
    ) -> RegisteredDashboard:
        if application_id is not None:
            raise UnknownRoleError(
                "an application id names an Entra ID app registration; on this deployment "
                "OspreyFlow creates the dashboard's own client: leave it out"
            )
        client_id = f"{DASHBOARD_PREFIX}{_slug(name)}"
        made = await self._call(
            "POST",
            "/clients",
            json=self._client(client_id, self._settings.oidc_audience or "osprey-conduit"),
        )
        if made.status_code == 409:
            raise DashboardExistsError(client_id)
        if made.status_code != 201:
            raise IdentityAdminRefused(
                f"the identity provider did not register the dashboard ({made.status_code})"
            )
        uuid = await self._uuid(client_id)
        if uuid is None:
            raise IdentityAdminRefused("the dashboard was registered but cannot be found")
        secret = str((await self._call("GET", f"/clients/{uuid}/client-secret")).json()["value"])
        account = (await self._call("GET", f"/clients/{uuid}/service-account-user")).json()
        attributes = {**(account.get("attributes") or {}), "clearance": [clearance],
                      "org_unit": [org_unit], "roles": ["reports_viewer"],
                      "receivable_handling_codes": ["P"]}  # fmt: skip
        await self._call(
            "PUT", f"/users/{account['id']}", json={**account, "attributes": attributes}
        )
        return RegisteredDashboard(
            dashboard=DashboardIdentity(client_id=client_id, account_id=str(account["id"]),
                                        clearance=clearance, org_unit=org_unit),
            secret=secret,
        )  # fmt: skip

    async def delete_dashboard(self, client_id: str) -> None:
        if not client_id.startswith(DASHBOARD_PREFIX):
            raise UnknownRoleError(f"{client_id} is not a dashboard identity")
        uuid = await self._uuid(client_id)
        if uuid is None:
            raise IdentityAdminRefused("no such dashboard")
        await self._call("DELETE", f"/clients/{uuid}")


__all__ = [
    "CONDUIT_ACCOUNTS", "DashboardExistsError", "DashboardIdentity", "IdentityAdmin",
    "IdentityAdminRefused", "OrganisationArrival", "PersonAccount", "PersonActionRefused",
    "RegisteredDashboard",
    "UnknownRoleError", "allowed_role",
]  # fmt: skip
