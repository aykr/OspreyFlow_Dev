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

## After rules-b's findings (the owner, 15 November 2026)

8. **MapTiler is dropped** from the list: its terms require the browser to call it unless MapTiler agrees in writing
   (ruling 2). It can come back for a client who holds that written agreement.
9. **Bedrock's read-only listing grant is approved**: `bedrock:ListFoundationModels` and `bedrock:ListInferenceProfiles`
   on the deployment's role, and the Bedrock control-plane host on the allowed-out list, in the Terraform.
10. **The model store's salt is never changed silently.** No in-place rotation in this build: a salt change is refused
    in words unless the operator confirms that every engine's key must be re-entered, and the engines are named; the
    guide documents it.
11. **OS premium: the obligation is said at the tick.** Its licence tick states, in words, that the organisation keeps a
    list of everyone with access to premium data and passes OS's end-user terms on; Admin › People's map access is the
    list's source. No new feature.

Also settled from the terms (PREBUILD_FINDINGS §9): Esri is live-only with no cache shared between analysts; OS premium
is live-only with a cache of at most 24 hours; OS Open Zoomstack may be prefetched. Correction recorded: ruling 7 is
already the rule as built (ADR-135 Amendment 2, 8 Nov: model keys entered in Admin, sealed in the gateway); the guide's
"never in the Admin area" is the part to correct.

## A first slice (the owner, 15 November 2026, late morning)

12. **Only the model form's first slice is built now**, beside v0.6.0, then the work stops until the owner says: the
    screen (M1), the key and a typed model name proved by one small call before Add (part of M2), and ADR-135
    Amendment 14 cut down to the slice (M4). Not in it: model listing, Bedrock listing (M3), any wider role.
13. **The map form waits** until the owner has used the model form on the demo. MapTiler is off; nothing is prefetched
    for Esri or OpenStreetMap's own servers.
14. **The administration guide's model-key passages are corrected in v0.6.0** (docs, with item 9's pass): a key has been
    entered in Admin › Models since ADR-135 Amendment 2.
