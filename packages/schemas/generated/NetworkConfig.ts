// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: false. Publish the Conduit's own port on the host in addition to the workspace's. Not needed to use the deployment — the workspace proxies /v1 — and turning it on widens the exposed surface by a whole tier. For an operator debugging the Conduit directly, or a second client that is not the Glass.
 */
export type ExposeConduit = boolean;

/**
 * What this deployment publishes to its host.
 *
 * `05_DEPLOYMENT.md` §7: "Every service on an internal network. Only the workspace and the
 * Conduit are exposed, behind a reverse proxy terminating TLS." Since the owner's decision of
 * 25 September 2026 (§2.6 item 1) **the workspace's own image is that reverse proxy** — its nginx
 * proxies `/v1` and the delta WebSocket to the Conduit on the internal network — so the normal
 * deployment publishes one port, not two, and the Conduit is reachable without being exposed.
 */
export interface NetworkConfig {
  expose_conduit?: ExposeConduit;
}
