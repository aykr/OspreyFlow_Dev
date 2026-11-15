# Admin forms: the owner's rulings, 15 November 2026

Asked by the orchestrator after the owner's prompt (`OWNER_PROMPT_2026-11-15.md`), before the build. These bind the two
amendments to be drafted: **ADR-147** (maps) and **ADR-135** (models; it changes decision 2's "never in the Admin area").

## Maps (ADR-147 amendment)

1. **Your organisation's map service: the installer allowlists its hosts.** `osprey.yaml` names the internal map hosts the
   deployment may reach (the installer's or platform team's decision). Admin may add any service on those hosts, by
   "Read the service", nothing typed by hand. Any other internal or private address stays refused under decision 2a, and
   the form names who must add the host.
2. **No key ever reaches a browser.** A provider that needs a key is always fetched through this deployment (the tile
   proxy), so the key stays on the server and the provider never sees analysts or the areas they view. A keyed provider
   whose terms forbid proxying is not offered, and the form says why. The direct route is only for a provider that
   needs no key and whose terms require it. (Explained to the owner: the direct route puts the key in every tile URL
   an analyst's browser requests, and tells the provider which areas each analyst views.)
3. **A provider whose terms forbid prefetching is added for live use only.** Prefetch areas cannot use it, and the form
   and Admin › Maps say why in words.
4. **A licence of our own: a tick plus the licence's reference, audited.** The reference (a contract or account number)
   is kept with the provider and shown in Admin › Maps. Who confirmed it, and when, goes in the audit.

## Both forms

5. **Key files encrypted at rest**, with a key held in the deployment's own secrets (the private secrets file on
   Small/Lite; the cluster's secret store or KMS on cloud-platform). A copied volume or disk image reveals nothing.
   Applies to the existing map key file as well as the new model key store.
6. **On cloud-platform, the full form, gated by the platform.** It works the same, keeping keys in the deployment's own
   secret store. Where a provider's host is not yet allowed out of the cluster, the form refuses in words and names the
   setting the platform team must add.

## Models (ADR-135 amendment)

7. **A model key may pass through the Conduit in transit only.** The Conduit hands it straight to the model gateway's own
   key store and keeps nothing: no file, log, error or audit text, tested end to end. The key check against the provider
   runs in the gateway, not the Conduit. The owner accepted this as the one way the change weakens today's rule; it is
   the rule maps already follow.

The owner's key rules 1 to 6 in the prompt stand as written. "Exposed through the admin interface" in the owner's
reply means **managed** there (set, replace, remove), never displayed (rule 1).
