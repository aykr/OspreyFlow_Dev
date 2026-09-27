"""The post-launch verify — the last step of the golden path, and part of "health-checked".

`06_DECISIONS.md` ADR-043's amendment (Accepted, 24 September 2026) specifies three assertions, not
two. The two-sided wording it replaces could not be built: measured against a real Keycloak 26.0, a
client holding the impersonation grant is issued a token for *any* subject in the realm including a
**disabled** one, so "refuse an out-of-scope subject" is a check that can never go red.

1. **Success** for the disposable verify subject, with that subject's own claims and nothing
   broader.
2. **Refusal of an unprivileged client** by Keycloak — the one refusal the realm actually enforces,
   and therefore the only realm-level containment there is to test.
3. **Refusal of a disabled subject by the Conduit's own pre-check** — because the realm will not
   refuse it. This is the assertion the amendment exists for.

There is no fourth, realm-level per-target assertion. A bounded attempt to configure one on Keycloak
26.0 failed three ways (`05_DEPLOYMENT.md` §2.1.1 and the amendment have the detail).

**The operator wording on failure is `07_BUILD_PLAN.md`'s, verbatim**, and it is an
IdP-configuration message rather than an access-problem one on purpose: the symptom an operator
otherwise meets is watches marked `"stopped"`, which reads as something wrong with an analyst's
clearance rather than with how this instance was set up — the exact wrong diagnosis for the fault.
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.realm import (
    CONDUIT_CLIENT_ID,
    REVOKED_SUBJECT,
    UNPRIVILEGED_CLIENT_ID,
    VERIFY_SUBJECT,
)
from principal_auth import (
    OidcResolverSettings,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalResolver,
    PrincipalRevoked,
)

#: `07_BUILD_PLAN.md`'s harness entry, verbatim. Not paraphrased: it is worded to be distinguishable
#: from whatever an analyst is later shown, so the two failure surfaces are never mistaken for one.
OPERATOR_FAILURE_MESSAGE = (
    "token exchange is not correctly configured on your identity provider; watches will appear "
    "stopped for every owner but the analyst who triggered them until this is fixed"
)


@dataclass(frozen=True)
class VerifyResult:
    assertion: str
    ok: bool
    detail: str


def _resolver(
    *, issuer: str, realm: str, client_id: str, secret: str, with_precheck: bool
) -> PrincipalResolver:
    # Nine real OIDC fields and nothing else. Until round 13b this had to build a whole
    # `ApiConfig` — inventing a Postgres host, user and password, and a Valkey port, none of
    # which the resolver ever reads — purely to satisfy a type that lived in `services/api`.
    # `packages/principal_auth`'s own `OidcSettings` is the nine fields, so the fabrication is
    # gone along with the import that forced it.
    return PrincipalResolver(
        OidcResolverSettings(
            oidc_jwks_url=f"{issuer}/realms/{realm}/protocol/openid-connect/certs",
            oidc_token_exchange_url=f"{issuer}/realms/{realm}/protocol/openid-connect/token",
            oidc_token_exchange_client_id=client_id,
            oidc_token_exchange_client_secret=secret,
            oidc_admin_users_url=(
                f"{issuer}/admin/realms/{realm}/users" if with_precheck else None
            ),
        )
    )


async def run_verify(
    *, issuer: str, realm: str, conduit_secret: str, unprivileged_secret: str
) -> list[VerifyResult]:
    """Runs all three against the running deployment. Never short-circuits: an operator wants every
    result, not the first failure, because two of the three failing together means something
    different from either failing alone."""
    results: list[VerifyResult] = []

    resolver = _resolver(
        issuer=issuer,
        realm=realm,
        client_id=CONDUIT_CLIENT_ID,
        secret=conduit_secret,
        with_precheck=True,
    )
    try:
        try:
            principal = await resolver.resolve_for_owner_detailed(VERIFY_SUBJECT)
            results.append(
                VerifyResult(
                    "1-exchange-succeeds-for-the-verify-subject",
                    bool(principal and principal.id),
                    f"resolved principal {principal.id!r} with clearance {principal.clearance!r}",
                )
            )
        except (PrincipalExchangeRefused, PrincipalExchangeUnavailable) as exc:
            results.append(
                VerifyResult("1-exchange-succeeds-for-the-verify-subject", False, str(exc))
            )

        # 3. The disabled subject, refused by this Conduit's own pre-check.
        try:
            await resolver.resolve_for_owner_detailed(REVOKED_SUBJECT)
            results.append(
                VerifyResult(
                    "3-disabled-subject-refused-by-the-conduit-precheck",
                    False,
                    "a disabled subject was exchanged — the pre-check is not in force, and the "
                    "realm will not refuse this on its own",
                )
            )
        except PrincipalRevoked as exc:
            results.append(
                VerifyResult("3-disabled-subject-refused-by-the-conduit-precheck", True, str(exc))
            )
        except (PrincipalExchangeRefused, PrincipalExchangeUnavailable) as exc:
            # Refused, but not by the pre-check — a different fault, and reported as one rather
            # than credited as a pass.
            results.append(
                VerifyResult(
                    "3-disabled-subject-refused-by-the-conduit-precheck",
                    False,
                    f"refused, but not by the pre-check: {exc}",
                )
            )
    finally:
        await resolver.aclose()

    # 2. The unprivileged client, refused by Keycloak itself.
    unprivileged = _resolver(
        issuer=issuer,
        realm=realm,
        client_id=UNPRIVILEGED_CLIENT_ID,
        secret=unprivileged_secret,
        with_precheck=False,
    )
    try:
        await unprivileged.resolve_for_owner_detailed(VERIFY_SUBJECT)
        results.append(
            VerifyResult(
                "2-unprivileged-client-refused-by-keycloak",
                False,
                "a client holding no impersonation grant was allowed to exchange",
            )
        )
    except PrincipalExchangeRefused as exc:
        # **The refusal has to come from the token endpoint, not from claim verification.**
        # `PrincipalExchangeRefused` covers both — "the IdP said no" and "the IdP said yes and the
        # token it returned did not verify" — and only the first is what this assertion claims.
        # Found by the mutation that was supposed to turn this red and did not: granting the
        # unprivileged client the impersonation role made the exchange succeed at the HTTP level,
        # and this assertion still reported green because the resulting token failed verification
        # for an unrelated reason. A refusal counted without reading why is a gate that cannot go
        # red, which is exactly what `CLAUDE.md` rule 15 is about.
        message = str(exc)
        refused_by_the_endpoint = "token exchange refused for owner" in message
        results.append(
            VerifyResult(
                "2-unprivileged-client-refused-by-keycloak",
                refused_by_the_endpoint,
                message
                if refused_by_the_endpoint
                else (
                    "the exchange was NOT refused by Keycloak — it succeeded and then failed for "
                    f"another reason, which this assertion must not count as a refusal: {message}"
                ),
            )
        )
    except PrincipalExchangeUnavailable as exc:
        results.append(VerifyResult("2-unprivileged-client-refused-by-keycloak", False, str(exc)))
    finally:
        await unprivileged.aclose()

    return sorted(results, key=lambda r: r.assertion)
