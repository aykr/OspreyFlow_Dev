// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: keycloak. The identity provider people sign in through.
 */
export type IdentityProvider = string;
/**
 * Default: uk-law-enforcement. The handling scheme every item is marked under.
 */
export type HandlingScheme = string;
/**
 * Default: default. The ontology the deployment starts from.
 */
export type Ontology = string;
/**
 * The alias of an organisation's own identity provider brokered by Keycloak. When set, the welcome page offers *Continue with organisation sign-in*, which goes straight to it (ADR-115 decision 3). Default: none — one *Sign in* to the OspreyFlow form.
 */
export type OrganisationSignIn = string | null;
/**
 * The provider's name as people know it, shown on the identity provider's own sign-in pages (for example 'Example Department account').
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
 * The protective marking shown where no case data is on screen: the welcome page, Home, the Ingest Studio and the Admin area; inside a case, the strip shows this or the highest marking on screen, whichever is higher (ADR-115 decision 2). One of the handling scheme's classifications. Default: the scheme's lowest.
 */
export type Marking = string | null;
/**
 * Default: config/real_data_exceptions.yaml. A path to the gitignored list, never its contents.
 */
export type RealDataExceptions = string;

/**
 * `05_DEPLOYMENT.md` §2.1's Governance screen: "Identity provider, handling scheme, ontology.
 * Ships with a UK law-enforcement scheme, a US criminal-intelligence scheme, and the default
 * ontology."
 *
 * `real_data_exceptions` is the **reference** ADR-049's Stage 2 §6 puts on the Governance panel —
 * a path to the local, never-committed exceptions list, not its contents. The list itself is
 * gitignored (`config/real_data_exceptions.yaml`, standing rule 3 / `CLAUDE.md` rule 9 /
 * ADR-035 §C3) and must stay that way: this field records where to look, exactly as §2.5 requires
 * of every credential, and for the same reason.
 */
export interface GovernanceConfig {
  identity_provider?: IdentityProvider;
  handling_scheme?: HandlingScheme;
  ontology?: Ontology;
  organisation_sign_in?: OrganisationSignIn;
  /**
   * Small on a server of your own only (ADR-114 Amendment 33 decision 4): the organisation's identity provider that `organisation_sign_in` names, which `ospreyflow install` and `ospreyflow repair-sign-in` register in Keycloak. Default: none — people sign in with accounts an administrator makes.
   */
  organisation_provider?: OrganisationProvider | null;
  marking?: Marking;
  real_data_exceptions?: RealDataExceptions;
}
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
}
