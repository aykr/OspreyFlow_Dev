// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The domain's HTTPS address
 */
export type Url = string;

/**
 * A cloud's managed OpenSearch (`05_DEPLOYMENT.md` §3b: Amazon OpenSearch Service).
 */
export interface ExternalSearch {
  url: Url;
}
