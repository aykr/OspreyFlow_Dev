# The GOV.UK demo's certificate, replaced 18 November 2026

A record, not a slice. Done outside the line, on the owner's word, in a session started outside the checkout (the
line's guard refuses any command that touches the demo, so the line itself did not do it). Nothing in the line's gates
ran on it. Source reports: `Claude outputs/ospreyflow_demo_certificate_2026-11-18/` (`STEP1_STOPPED.md`,
`STEP2_REPORT.md`); the folder is git-ignored, so this file is the committed record.

| | Before | After |
| --- | --- | --- |
| Issuer | Let's Encrypt | Google Trust Services |
| Names | the demo's three | the same three |
| Key | ECDSA P-256 | ECDSA P-256, a new key |
| Expires | 10 February 2027 | **16 February 2027, 05:59 UTC** |
| Renewal | not working (a manual DNS step; nothing installed or reloaded the certificate) | automatic: lego by DNS-01 through the registrar's API, from a daily systemd timer at 03:30 UTC |
| First renewal due | | **18 January 2027, 03:30 UTC** (lego renews with a third of the life left) |

- **Checked from outside:** all three names serve the new chain and verify (OpenSSL return code 0; curl on macOS).
- **Outage:** about one second, the proxy container restarting. Every other container's uptime was unchanged. Each
  automatic renewal repeats that restart, roughly every 60 days.
- **Rehearsed first** against the issuer's staging service: obtain, a re-run that skipped, and a forced renewal whose
  deploy hook fired (the staging hook only printed a marker).
- **Way back:** the old certificate and key are in a dated, root-only backup folder on the server, valid until
  10 February 2027; restore them and restart the proxy container, then disable the renewal timer (the report has the
  exact steps).
- **Old renewal retired:** the certbot renewal file was renamed, not deleted.
- **Left in place:** the certbot package and timer; the Caddyfile, compose file, other containers, airbyte, firewall.
- **DNS:** the line's own challenge records were created and removed by lego. Five stale `_acme-challenge` records
  (three from 12 November, two on the bare domain that appeared on 18 November after 06:30 UTC and were not made by this
  task) were deleted on the owner's word; their values are in the source report. What made the two bare-domain records
  was not identified.
- **Open notes, not backlog rows yet:** the certificate's contact address has no mail server, so an issuer notice
  would bounce; the server's login banner says a restart is required.

**Backlog rows closed by this:** C194 (the demo's certificate renewal, "before 10 Jan 2027"), the certificates'
automatic-renewal half of L13, and step 5 of "First, on the owner's word" in `BACKLOG.md`. D15's "certificate renewal
(expires 10 February 2027)" is met; PL2 keeps connection limits and the Java licence notice.

**Not measured by the line:** the first automatic renewal has not yet happened. The rehearsal on staging is the only
evidence it works; the real one is due 18 January 2027. Check the server's renewal log that morning.
