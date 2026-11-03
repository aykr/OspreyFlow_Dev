// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
