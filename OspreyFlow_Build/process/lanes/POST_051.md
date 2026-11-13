# After v0.5.1 · the steps and who does them (the owner, 13 November 2026: "carry on with the post-0.5.1 steps")

Kept by the orchestrator. **The rule that protects the release:** these steps are built now, on their own branches,
offline where they can be; **none merges into main until step 8 of `finish.tsv` (the release candidate) is cut**, so
v0.5.1 is the commit that passed R1 plus the steps already on its path. After the cut, they merge in the order below.
Nothing here touches osprey-small until its own deploy step, on the orchestrator's word, after a backup.

| # | Step | Lane | Size | Needs from the owner |
|---|---|---|---|---|
| A | **Part 3: ospreyflow.app beside the GOV.UK demo** on the one server (`process/lanes/demo/PART2.md`): two Small deployments by name, their own Compose projects and ports, one shared GPU, an edge router in front by host name, a certificate for ospreyflow.app (DNS-01, as govuk.ospreyflow.app's). Product changes first (the doctor's 443/2480 checks per deployment, `--name` for Small, the Compose project per name, the model engine shared), then the edge, then the second deployment. | platform | L | the DNS records for ospreyflow.app (A, and the `_acme-challenge` TXT when asked); whether ospreyflow.app has the key prompt |
| B | **Test hygiene from CARRIES:** test_webapp_preflight's GPU case on a GPU host; the shared real-Caddy fixture (out of test_access_key_proxy.py); test_webapp_sign_in under load. | platform-b | S | — |
| C | **T1's rest** (faster live runs: marks, sleeps, the ArcadeDB waits). | admin, after pg | M | — |
| D | **The owner's two rulings, then their builds:** (1) the Conduit's 48 pools: one shared pool, or sizes from settings (R1 finding 15b); (2) a disabled model engine's egress: close it from Admin's state, or say in Admin it stays open (ADR-135 Am 10). | as ruled | M each | **two rulings** |
| E | **The cloud-platform's sizing:** requests ~26.6 GiB against < 8 GiB used (R1's memory table); the poc shape's requests from measured use, with the headroom stated. | platform, after A | S | — |
| F | **P7a, P8, P9b** (the production shape on kind; nothing on a shared disk; alerts, PDB drain, volume expansion). | platform | L | after the client's install (from 20 Nov) |

The CARRIES rows not named here stay there, each with its own lane, and are taken as the lanes free up.
