# Slice AD1d · AD1 · The models a key may use are listed for the form to offer (ADR-135 Amendment 14's deferred item); after AD1c; every finding in it is the owner's

- **Build id:** AD1 (the Admin model form). **The owner's rulings of 23 November 2026:** "AD1d: agreed as a part of its own, after AD1c. **Every finding in it is mine.**" (He had asked whether Amendment 14's own text still requires "the models chosen from what the gateway found": it does not; the amendment is cut to his first slice and lists this in "Not in it".)
- **Dial setting:** balanced
- **Rounds limit:** the dial's (8)
- **After:** AD1c merged. **No row in `slices.tsv` yet; the conductor adds it when AD1c has merged.**
- **Status of this brief:** written by the conductor on 23 November 2026, as a draft for the owner to read before a builder starts; **read, not measured: re-read every line named.**

## What the specification says it left out

ADR-135 Amendment 14 (`OspreyFlow_Build/spec/06_DECISIONS.md`, about line 41462 on the AD1b branch; on main once AD1a merges): "**Not in it:** listing the models a key may use (the draft's wildcard route and `check_provider_endpoint`), Bedrock's listing grant (ruling 9), and the map form (ADR-147's amendment)." The administration guide says "Listing the models a key may use is not built yet". The admin-forms findings file (`OspreyFlow_Build/process/lanes/admin-forms/PREBUILD_FINDINGS.md` §1 and §5.3's draft) holds the original design: the models chosen from what the gateway found, or a typed name proven by one call.

## What (to be settled with the owner before a builder starts; the conductor's reading)

1. **A listing route on the gateway side** (`check_provider_endpoint` and the draft's wildcard route): given a key the administrator has typed (never stored by the page, never logged, never shown), the Conduit asks the provider for the models that key may use and returns **names only** (never any part of a key), for the form to offer beside the typed name. A typed name stays possible and is still proven by one call before **Add**.
2. **The Bedrock listing grant (ruling 9)** as its own sub-item: what the gateway's own role must be granted to list, and how that is said in the guide.
3. **The key rules the owner set for AD1** hold throughout: replace and remove, never reveal; the key field cleared after a save or a refusal; no key text in any log, answer or audit row; a refused listing says so in words and leaves nothing behind on the gateway.
4. **Tests, red first, planted at the shape the code really sees (rule 15):** a gateway and provider stand-in that **models the real ones' refusals** (a key the provider refuses, a provider that answers a list with more than the key may use, a timeout, a listing grant missing), and the key-text checks of AD1b's `test_stale_engine_keys_are_named.py` extended to the listing's answers.

## Every finding in this part is the owner's

**It handles a key.** A finding that names a key, a credential or a security rule is **stopped and reported to the owner, never accepted narrower, never accepted on the standing line.** The conductor does not choose between options on such a finding.

## Out of scope

Anything AD1c does (the fourth route, the orphaned tokens); the map form (ADR-147's amendment); the protected files.
