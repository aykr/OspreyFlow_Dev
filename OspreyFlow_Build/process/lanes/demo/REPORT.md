# Demo lane · Part 1 · osprey-small rebuilt from main b380d456 (12 November 2026)

1. Code: main b380d456 copied by `git archive` + rsync as `osprey`; venv re-synced; `install --build` (HEAD's v0.5.0 tag would have pulled v0.5.0 images). MET: install log "owned images built from this checkout", verify 3/3.
2. Stores fresh: nine volumes removed, ollama-models and whisper-models kept. MET: `/root/rebuild-2026-11-12/4-uninstall.txt`.
3. Services healthy. MET: `ospreyflow status`, 16 running, every health-checked one healthy.
4. Sign-in, four demo accounts, Keycloak form (PKCE, osprey-glass). MET: `demo_checks.py signin`, 4 PASS, re-run after keycloak restarted.
5. Packs loaded, analyst an Editor of each. MET: five cases; Explore counts match the seeds' (`case_checks.py`).
6. PI documents and Questions. NOT MET: `422 no_documents` (PI's text reports load in chapter 4). Local model answers directly: qwen2.5:14b-instruct, 59 s cold, 100% GPU.
7. Ledger lists and alerts. PARTIAL BY DESIGN: list subscribed but unread; rule live; alerts come from the monitoring week, mid-demo (DEMO_GUIDE §8b).
8. Dashboards for the report viewer. NOT MET: case Reports open, but no Superset dashboard exists (needs a dashboard identity and its secret, which is the owner's to set up).
9. Admin rule rights. MET: holds deploy_rules, no author_rules; role not added.
Post-seed backup: `/srv/ospreyflow/backups/small/20261112T173107Z-small-2be985a…`. Finding: glass.json version and backup names read 2be985a.

## Decisions taken
- Demo accounts: Small refuses them (ADR-114 Am 33). The owner chose (A): seed OSPREY_DEMO_ADMIN_PASSWORD, then ANALYST, then `repair-sign-in`. This goes round the gate, for tonight only; remove the four accounts before anything goes public.
- `sendable_handling_codes: [P]` was refused without a fallback. Added `hosted_fallback: gemini`, an inert marker no service reads. Orchestrator accepted; CARRIES row.
- `post_ingest_resolution: false` and a second apply, for PI (the brief's `demo_packs: []` gap). Orchestrator approved.
- Post-seed backup taken before the checks. Orchestrator approved.

Commits: this report and the friction row only. Requests: none open. Nothing of mine is running; the server is frozen.

## Later the same evening (owner's word, approved in this window): osprey-small moved to https://govuk.ospreyflow.app
- Backup before the move: `/srv/ospreyflow/backups/small/20261112T180657Z-small-2be985a…`.
- Let's Encrypt certificate by manual DNS-01 (certbot 2.9.0, installed by apt): three names, expires 10 Feb 2027.
- Copied into `/etc/ospreyflow/tls/govuk.ospreyflow.app.{crt,key}` (osprey; the key mode 600).
- `osprey.yaml`: `public_origin` and the TLS paths changed, `tls.ca` removed. Copy kept as `osprey.yaml.before-govuk-app-20261112T181854Z`.
- One apply, then repair-sign-in. Every check passes at the new address: services, certificate, four sign-ins, a case, brand.
- Switch scripts follow `public_origin`; not run.
- Open: `install.yaml` still names the old address. Certificate renewal is manual.
