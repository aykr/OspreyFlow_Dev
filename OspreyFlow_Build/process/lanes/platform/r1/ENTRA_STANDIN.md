# R1 · Entra ID by a stand-in, and what it cannot prove

The owner's ruling (13 November 2026, through the orchestrator): **a stand-in now, the real tenant later.**

## The stand-in

A pod in the kind cluster answers as `login.microsoftonline.com` (CoreDNS, inside the cluster only). It serves
the stand-in tenant's OpenID discovery and its signing keys, and refuses another tenant (AADSTS90002).

**From v0.5.2 it signs** (step 8, `gates/r1_kind_servers.py entra`), because Superset and the report sync sign
in through Entra (ADR-148 Amendments 9 and 10) and nothing outside the cluster can sign for them:

- **A throwaway key per run, inside the stand-in.** It makes an RSA key at start, holds it in memory and never
  writes it out; its public half is published in the tenant's keys. Each run's key is new.
- **`/authorize`**: one person (the first administrator), signed in at once, with no form. It takes a code
  request with PKCE (the Glass) or without (Superset, which then proves itself with its secret).
- **`/token`**: `authorization_code`, giving a v2.0 access token for the API's delegated scope (`scp`) and an
  ID token with the nonce, the `sub` pairwise per application; and `client_credentials`, giving an app-only
  token (`idtyp: app`, the client's app roles, no `scp`).
- **The tenant's registrations** (`gates/r1_kind.py entra_config`): the API and its scope, and the Glass, from
  R1's settings; Superset and the report sync, from `gates/r1_kind_entra.yaml`. Their secrets are made per run
  and kept in the run's state folder alone. That file's Superset redirect path and report-sync app role are
  to be aligned with platform-b's and admin's render before v0.5.2's R1.
- **What it refuses, with Entra's own error and code:**
  - another tenant (90002);
  - an unknown client (700016);
  - a redirect URI not registered (50011: shown on its page, never redirected to);
  - a scope the client was not granted, so no `scp` (65001, `consent_required`);
  - a missing or wrong secret (7000218, 7000215);
  - a code expired, already used, or another client's or another redirect's (70008, 70000);
  - a PKCE verifier that does not match (50148);
  - a client-credentials scope not `<resource>/.default` (1002012), or of another resource (500011);
  - any other grant (70003).
- **The tests:** `tests/test_r1_entra_standin.py` holds each refusal, offline on loopback. It also passes a
  Glass sign-in by code and PKCE through the Conduit's real resolver, configured as the poc render configures it.
  Each check was shown red: PKCE unchecked, the granted scope unchecked, the secret uncompared
  (`v052-standin/red-first.txt`).

The tokens R1's checks craft are still minted by `gates/r1_kind.py token`, with a key that never enters the
cluster. They are the ones Entra would never issue but the Conduit must refuse: another tenant, another
audience, expired, no `oid`, a group overage, a guest, an app-only token sent to a person's route, and a key
the tenant never published. Those tokens are Entra v2.0 access tokens in the shape ADR-148 Amendment 8
expects. The Conduit is not changed and does not know that a stand-in is being used.

Roles are not Entra app roles. Under Amendment 8 point 1 they belong to the deployment, kept by tenant and object
id in its own Postgres. So "an unassigned app role" is checked as what it means here: a person of the tenant
whom no administrator gave a role.

## What it refuses (rule 15), each through the real resolver behind the real ingress (`r1_kind.py check`)

| Token | Expected |
|---|---|
| Another tenant's (its `tid` and issuer) | 401 |
| Another audience | 401 |
| Expired | 401 |
| App-only (no `scp`, `idtyp: app`, `roles`) | 401 or 403 |
| A guest's (`idp` another tenant) | 401 or 403 |
| No `oid` | 401 |
| A group overage (`_claim_names` in place of `groups`) | 401 or 403 |
| Signed by a key the tenant never published, under its `kid` | 401 |
| A person of the tenant given no role | signs in with no role; 403 for Admin › People and a new case |

## What it cannot prove about a real tenant

- **The tenant's configuration.** Whether the two app registrations exist, whether the API exposes the scope and
  the Glass is granted it, and whether `requestedAccessTokenVersion` is 2. The stand-in's tokens are v2.0 because
  we minted them that way.
- **The claims the tenant actually sends.** Whether the claims mapping policy or optional claims put the
  clearance, unit and handling codes where `cloud_platform.claims` says. The stand-in's tokens carry them because
  we wrote them in.
- **Who Entra lets sign in at all.** *Assignment required* on the enterprise application, Conditional Access, MFA
  and the guest policy are applied by Entra before a token exists. AADSTS50105 never reaches the deployment.
- **The browser's sign-in.** Entra's sign-in page, consent, MFA and the token's renewal. The stand-in signs its
  one person in at once, with no page. It checks the code exchange (PKCE, the secret, the registered redirect),
  but not what a person sees, and the stand-in's registrations are ours, not the tenant's.
- **Key rollover and Entra's own key discovery** in a real outage, and v1.0 tokens (`sts.windows.net` issuer).
- **Network reach.** The Conduit reaching the real `login.microsoftonline.com` through the client's egress.

## The steps against the real tenant

These are in the install runbook as **step 8, "Against the client's real tenant"**. That section is marked as
no block to run, because each item needs a person at a browser. The platform team does them once, with the
client's Entra administrator:

1. The token version (`requestedAccessTokenVersion` 2).
2. The first administrator's sign-in, clearance, unit and codes.
3. A person given no role.
4. Who may sign in at all (*Assignment required*, AADSTS50105).
5. A guest.
6. More than 200 groups.
7. The signing key's roll.
