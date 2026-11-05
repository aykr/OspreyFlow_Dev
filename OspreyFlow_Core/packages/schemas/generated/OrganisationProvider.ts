// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The provider's name as people know it, shown on the welcome page's button (Continue with <label>) and on the identity provider's own sign-in pages (for example 'Example Department account').
 */
export type Label = string;
/**
 * The provider's issuer, an https:// address; its discovery document is read from <issuer>/.well-known/openid-configuration (for Entra ID, https://login.microsoftonline.com/<tenant>/v2.0).
 */
export type Issuer = string;
/**
 * The application (client) id the organisation registered for OspreyFlow.
 */
export type ClientId = string;
/**
 * ADR-114 Amendment 33, 'Step 33': true joins a person arriving through the organisation to the OspreyFlow account holding the same email address, automatically, with its roles and clearance. Off by default: a person whose email an account holds is refused in words, and an administrator joins them in Admin, People and roles. Turn it on only with the organisation's security officer's written sign-off that every address its provider gives is verified and cannot be set by the person who holds it: anyone who can make the provider give an address takes over the account that holds it (the 2023 'nOAuth' account takeovers).
 */
export type TrustEmail = boolean;

/**
 * ADR-114 Amendment 33 decision 4: the organisation's own identity provider (OpenID Connect —
 * Entra ID, ADFS, an internal Keycloak), brokered by the deployment's Keycloak. Names and
 * addresses only: the client secret is `OSPREY_ORG_SIGN_IN_SECRET` in the installer's
 * environment, kept in `deployment.env` and set through Keycloak's admin API, never here
 * (`05_DEPLOYMENT.md` §2.5). A person arriving through it gets no role and no clearance until an
 * administrator grants them (the owner's answer 6: no group-to-role mapping).
 */
export interface OrganisationProvider {
  label: Label;
  issuer: Issuer;
  client_id: ClientId;
  trust_email?: TrustEmail;
}
