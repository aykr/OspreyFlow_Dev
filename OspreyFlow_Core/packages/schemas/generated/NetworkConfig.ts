// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: false. Publish the Conduit's own port on the host in addition to the workspace's. Not needed to use the deployment — the workspace proxies /v1 — and turning it on widens the exposed surface by a whole tier. For an operator debugging the Conduit directly, or a second client that is not the Glass.
 */
export type ExposeConduit = boolean;
/**
 * Default: http://ospreyflow.localhost. The origin a browser uses to reach the Glass; the identity provider is `id.` and the dashboards `bi.` in front of the same host, with the same scheme and port, and the front proxy publishes that port (ADR-114 Amendment 4). `06_DECISIONS.md` ADR-050 objection 2's resolution: the identity-provider realm is rendered from this value at apply time and the Glass's public client is registered with an exact redirect URI and post-logout URI derived from it — no wildcards. Change this to move the deployment to another name or port; nothing else needs to agree with it.
 */
export type PublicOrigin = string;
/**
 * The server certificate, then its intermediates, in PEM: an absolute path.
 */
export type Certificate = string;
/**
 * The certificate's private key in PEM, unencrypted: an absolute path. Owned by the installing account, mode 600; the front proxy runs as that account to read it.
 */
export type Key = string;
/**
 * Optional: the organisation's root certificate (PEM), an absolute path. With it, the certificate's chain is checked to reach it, and the host's own tools trust it.
 */
export type Ca = string | null;
/**
 * Small on a server of your own, with network.tls only: also publish port 80, and only to send people to the https:// address. Default: false — port 443 alone.
 */
export type RedirectHttp = boolean;
/**
 * Small on a server of your own, with network.tls only: the one address of the server the front proxy publishes on. Default: none — every interface.
 */
export type ListenAddress = string | null;

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
  public_origin?: PublicOrigin;
  /**
   * Small on a server of your own only (ADR-114 Amendment 33): the organisation's own certificate and key, served by the front proxy with no certificate management and no call out. Default: none — Small's front proxy obtains a certificate itself, which needs a public name and the internet.
   */
  tls?: TlsFiles | null;
  redirect_http?: RedirectHttp;
  listen_address?: ListenAddress;
}
/**
 * ADR-114 Amendment 33 decision 3: the organisation's own certificate for a Small on a server
 * of its own. Paths on the server, absolute; the front proxy mounts the two files read-only and
 * the key is never copied (not into the deployment folder, not into a backup). Checked before
 * anything starts by `harness/tls_check.py`.
 */
export interface TlsFiles {
  certificate: Certificate;
  key: Key;
  ca?: Ca;
}
