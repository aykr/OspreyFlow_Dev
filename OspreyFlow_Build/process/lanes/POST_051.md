# After v0.5.1 · the steps and who does them (the owner, 13 November 2026: "carry on with the post-0.5.1 steps")

Kept by the orchestrator. **The rule that protects the release:** these steps are built now, on their own branches,
offline where they can be; **none merges into main until step 8 of `finish.tsv` (the release candidate) is cut**, so
v0.5.1 is the commit that passed R1 plus the steps already on its path. After the cut, they merge in the order below.
Nothing here touches osprey-small until its own deploy step, on the orchestrator's word, after a backup.

| # | Step | Lane | Size | Needs from the owner |
|---|---|---|---|---|
| A | **Part 3: ospreyflow.app beside the GOV.UK demo** on the one server (`process/lanes/demo/PART2.md`): two Small deployments by name, their own Compose projects and ports, one shared GPU, an edge router in front by host name, a certificate for ospreyflow.app (DNS-01, as govuk.ospreyflow.app's). Product changes first (the doctor's 443/2480 checks per deployment, `--name` for Small, the Compose project per name, the model engine shared), then the edge, then the second deployment. | platform | L | the DNS records for ospreyflow.app (A, and the `_acme-challenge` TXT when asked); **no key prompt on ospreyflow.app** (the owner, 13 Nov) |
| B | **Test hygiene from CARRIES:** test_webapp_preflight's GPU case on a GPU host; the shared real-Caddy fixture (out of test_access_key_proxy.py); test_webapp_sign_in under load. | platform-b | S | — |
| C | **T1's rest** (faster live runs: marks, sleeps, the ArcadeDB waits). | admin, after pg | M | — |
| D1 | **The Conduit's pool sizes from settings** (the owner, 13 Nov; R1 finding 15b; ADR-114 Am 45): today's figures the default, the Postgres minimum derived from them. | admin, after pg | M | — |
| D2 | **A disabled engine's egress closed** (the owner, 13 Nov; ADR-135 Am 11): the render reads Admin's enabled set. | platform-b, after B | M | — |
| E | **The cloud-platform's sizing:** requests ~26.6 GiB against < 8 GiB used (R1's memory table); the poc shape's requests from measured use, with the headroom stated. | platform, after A | S | — |
| F | **P7a, P8, P9b** (the production shape on kind; nothing on a shared disk; alerts, PDB drain, volume expansion). | platform | L | after the client's install (from 20 Nov) |

The CARRIES rows not named here stay there, each with its own lane, and are taken as the lanes free up.
