# v0.6.2 · the backlog (kept by the orchestrator, 17 Nov 2026)

The next release's list, in one place. Not started: the owner opens v0.6.2. Sources: `v060/RULINGS.md` (the owner's
15 Nov list, which became v0.6.2's when the v0.6.1 patch went first; the 16 Nov findings) and the owner's word of 17 Nov.

## First, on the owner's word (17 Nov ~06:40Z): the default-themed demo, ospreyflow.app (was Part 3)

Stopped 16 Nov ~18:10Z (RULINGS "Part 3 moves"); lane `platform` closed at 63dde62 with its HANDOFF. Order:

1. **Named Small deployments get their own image tags** (`harness/render.py:601`): today every build-from-source
   deployment on a machine shares `osprey/<service>:local`, so building a second one moves the first one's tags (it
   happened to GOV.UK on 16 Nov; repaired with compose `build` only). Red first (rule 15): a test that renders two named
   Smalls and fails while their tags are equal.
2. **The install's sign-in step on a named Small reads `deployments/small`** (`cli/ospreyflow/main.py:1056`;
   `repair-sign-in` already uses `ctx.deployed().name`). Red first.
3. **DNS for ospreyflow.app**: the Porkbun API key has no "dns" scope. The owner's: give it the scope in Porkbun's API
   Access, or add the records by hand.
4. **Then the demo**, beside GOV.UK on the test server: a GOV.UK backup first, the one-line notice, and a check that
   GOV.UK's containers and tags are unchanged afterwards. The alternative (install from v0.6.1's published images, whose
   names are their own) avoids 1 but not 2.
5. The certificates' automatic renewal (item 7's second half).

## The owner's list (15 Nov), carried

- The two Admin forms: model engines and map providers, the key given in the screen (`admin-forms/`; the model form's
  first slice on `lane/platform-admin-forms` 9f6b2c6, not merged)
- Suppression taking effect (R7 step 2)
- People shown by name
- A model allowance per visitor
- Laurium's document reading from a screen
- The dead batch job's status
- Entra groups to roles
- Scheduled loads while the owner is away
- A disabled engine's way out closed
- Connection limits from settings
- Fine-grained access control on search
- The production-shape work
- Item 23, the cloud-platform shape's memory sizes from measured use
- Bedrock beyond London (AWS's EU profile, for current Claude models): to decide (ruling 17)
- (The websites ospreyflow.org and .net: published 16 Nov, done.)

## Findings from the GOV.UK rebuild and the v0.6.1 patch (16 Nov)

- The CLI follows the recorded home over the current folder on install (`home.py` `find_product`); every command needs
  `OSPREYFLOW_HOME` today.
- A fresh install from a git archive cannot seed demo packs (`seed_internal.py:611`, no `.git`).
- The places stage attaches the gazetteer to no case.
- `apply` says "nothing was started again" while a service is down, and names `start --name default` on Small.
- `demo add` does not feed the search index (the install built it before the packs loaded).
- Gemini's role is the bare id (`gemini-3.8-flash`; `ModelProviderConfig.route()` adds the prefix): the guide and the
  rebuild sheet say so.
- `apply` does not remake an engine's entry in the gateway's database.
- Test the connection reports the provider's own refusal (a 503's words) rather than "could not be reached".
- The worker_isolation SERIAL gap for `test_scheduler_lifespan`.
- The guides' screenshots, with v0.6.1's Ask drawer capture.
- The release steps' step 10 needs a Docker daemon for `harness.signatures`: run it on the test server (as for v0.6.1),
  and say so in `RELEASE_STEPS.md`.

## Findings from the owner's laptop reinstall (17 Nov)

- A fresh clone of the release refuses `ospreyflow install --mode lite --starter ospreyflow-crime --yes`: "osprey.yaml
  already exists and differs from what these answers make", though the file is the checkout's own committed one. A
  client's first install should not need `--force`: treat an unmodified committed `osprey.yaml` as replaceable.
  Red first: a test installing a starter over a clean checkout.
- A Lite deployment from before v0.6.0 has no way forward but a fresh install, and `backup` needs it running; the owner's
  was archived cold (volume tarballs) before `uninstall`. The guides could say so for Lite.
- (17 Nov, the owner on the GOV.UK demo) **Invite a person** offers a clearance and handling codes above the inviter's
  own: the demo admin (OFFICIAL, P) picked OFFICIAL-SENSITIVE with P, C, R and got 403 `above_your_clearance`
  (`app.py` `_within_your_reach`, ADR-114 Am 5). The refusal shows only in the form's intro text, so the Invite button
  seemed to do nothing. Offer only what the admin can give, and put the refusal by the button (an error summary).
- (17 Nov, laptop) The first install's `compose up -d --wait` hit apply's 1,800 s limit (`harness/apply.py:378`) with
  no container created, though the three images still missing then pulled in 49 s by hand; the re-run went through.
  Pull before `up` as its own step with progress, so a stalled pull is named rather than timed out.
