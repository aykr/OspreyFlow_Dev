# R1 · Entra ID by a stand-in, and what it cannot prove

The owner's ruling (13 November 2026, through the orchestrator): **a stand-in now, the real tenant later.**

## The stand-in

A pod in the kind cluster answers as `login.microsoftonline.com` (CoreDNS, inside the cluster only). It serves
the stand-in tenant's OpenID discovery and its signing keys, and refuses another tenant (AADSTS90002). The tokens
are Entra v2.0 access tokens in the shape ADR-148 Amendment 8 expects: `aud` the API's application id, the
tenant's issuer, `tid`, `oid`, `azp` the Glass's application id, a pairwise `sub`, the delegated `scp`, the
clearance claim and the groups. They are minted on the server with a key that never enters the cluster
(`gates/r1_kind.py token`). The Conduit is not changed and does not know that a stand-in is being used.

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
- **The browser's sign-in.** The Glass's PKCE redirect, consent, the redirect URIs registered for the Glass's
  name, and the token's renewal. R1 calls the Conduit with bearer tokens, so no browser signs in.
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
