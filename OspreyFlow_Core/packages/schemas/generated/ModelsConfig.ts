// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: true — no hosted fallback
 */
export type LocalOnly = boolean;
/**
 * Default: none. A provider name, never a credential.
 */
export type HostedFallback = string | null;
/**
 * Default: empty. Which handling codes may leave for a hosted model.
 */
export type SendableHandlingCodes = string[];

/**
 * `05_DEPLOYMENT.md` §2.1's Models screen: "Local only, or local with a named hosted fallback
 * — and if hosted, which handling codes may be sent to it. **Defaults to none**."
 *
 * The default here is that sentence, enforced rather than described: no hosted fallback, and an
 * empty set of sendable handling codes. `04_VAULT_BACKEND.md` §4's egress exception is off unless
 * something turns it on.
 */
export interface ModelsConfig {
  local_only?: LocalOnly;
  hosted_fallback?: HostedFallback;
  sendable_handling_codes?: SendableHandlingCodes;
}
