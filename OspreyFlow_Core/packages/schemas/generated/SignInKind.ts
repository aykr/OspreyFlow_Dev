// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "keycloak" | "entra";

/**
 * `GET /v1/admin/sign-in`: how this deployment's people sign in (ADR-148 Amendment 8), so Admin
 * › People offers what it can do: invite on Keycloak; add by object id on Entra ID, where Entra
 * holds the accounts.
 */
export interface SignInKind {
  kind: Kind;
  [k: string]: unknown;
}
