// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: keycloak (03_CONDUIT_MIDDLEWARE.md §6)
 */
export type IdentityProvider = string;
/**
 * Default: uk-law-enforcement
 */
export type HandlingScheme = string;
/**
 * Default: default
 */
export type Ontology = string;
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
  real_data_exceptions?: RealDataExceptions;
}
