# AD4 · Admin › Themes: where the theme's settings are kept and who may change them (a draft decision record, for the owner)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. **Not in the decision log and not applied:** if the owner accepts it, it becomes an
amendment of ADR-152 (decision 14 and exception X8) written into `spec/06_DECISIONS.md` by the orchestrator, with its
number reserved in `spec/ADR_RESERVATIONS.md` first. No row in `slices.tsv`; no builder starts from this paper.

**Where AD4 comes from.** The plan page is not on the server, so this reading is taken from the decision log. ADR-152
decision 14 (`OspreyFlow_Build/spec/06_DECISIONS.md` about lines 41177 to 41214) says that "when Admin › Themes is
built" the menu offers the department's name, its logo, the service name, the phase, the banner's words and the GOV.UK
identity switch, behind `administer_system`, kept on ADR-147's *Admin › Maps* pattern, and read through
`GET /v1/appearance`. That is exception X8 (about line 41152). ADR-152 Amendment 1 point 4 (about lines 41858 to 41868)
says "**AD4 builds the wider Themes list**": header and footer links, standard wording and statement links join decision
14's list. ADR-152's own "Not decided here" (about line 41277) leaves open "when Admin › Themes is built". **Question 0
for the owner: is AD4 this, and only this?**

## What exists today (read on 25 November 2026 at `4f77858a5`; re-read, lines move)

- **The settings model.** `AppearanceConfig`, `OspreyFlow_Core/packages/schemas/deployment.py:1708`. Fields: `brand`
  (:1717), `service_name` (:1721), `organisation` (:1726), `phase` (:1731), `banner_text` (:1735, one line of at most
  200 characters, validator :1768) and **`govuk_identity` (:1744, default false, left out of every dump while false,
  strictly a boolean, validator :1759)**. `told()` (:1776) is what the Glass and the sign-in page are told. **There is
  no `logo` field** and no field for links, standard wording or statements. The docstring (:1713) already says "the
  Admin console's Appearance tab is to write the same section". It is the `appearance:` section of `OspreyConfig`
  (:2188). *Decision 14 cites `deployment.py:1656`; the class is now at 1708 (a citation to correct with this record).*
- **How the settings reach people today.** `render_glass_settings` (`OspreyFlow_Core/harness/site.py:443`) writes
  `"appearance": config.appearance.told()` (:472) into `glass.json`. That file is mounted read-only as
  `/deployment.json` (`harness/render.py:1160`; written at :2201). *Decision 14 cites `render.py:1045`; it is now 1160.*
  **The page service does not read the appearance at all.** Its one brand-derived setting is `OSPREY_PAGES_TREE`
  (`harness/pages_service.py:457`, read at `apps/pages/server/config.ts:288-289`). The GOV.UK tree's header is the
  literal word "OspreyFlow" (`apps/pages/tree-govuk/layout.njk:20`), with no footer, no service name and no links, and
  the file says the identity switch is not drawn yet (:4-5).
- **The identity switch is a build-time setting, not only a page setting.** The renderer passes
  `--build-arg OSPREY_GOVUK_IDENTITY=1` to the workspace image only when `appearance.govuk_identity` is on under
  `govuk` (`apps/workspace/Dockerfile:59`; `harness/render.py:311-313` `wants_govuk_identity`, used at :655, :1098 and
  :2158; `harness/cloud_platform/__init__.py:1202`). `apps/workspace/scripts/sync_govuk_assets.mjs:13` writes the GDS
  Transport font and the crown image only then: "Off, this writes no font and no image". The renderer refuses the switch
  on a render that pulls a published workspace image (`render.py:284-298`). **So a switch turned on in Admin cannot
  bring in a typeface the running image does not hold.** This is the main finding of this paper (question 3).
- **The sign-in page is rendered at install.** `render_login_theme` (`harness/keycloak_theme.py:401`) writes the
  service name (:416), organisation, phase, banner words and `govukIdentity` (:444-454) into the theme. It is called by
  `harness/apply.py:1419`, `scripts/refresh.py:255` and `harness/cluster.py:491`. `harness/govuk_chrome.js` reads them
  from `window.OSPREY_GOVUK` (:36, :86). A change made in Admin would not reach it (decision 14's own "not checked",
  question 25).
- **The pattern decision 14 names: *Admin › Maps*** (`OspreyFlow_Core/services/api/map_admin.py`; header :1-26).
  `osprey.yaml`'s `map:` is where a deployment starts. The first change in Admin writes `maps.yaml` (`SETTINGS_FILE`,
  :76) in `/run/osprey/map-settings` (:78), mode `600`, by an atomic write (`_write_private`, :120-131). From then on
  that file replaces `map:` whole. One change at a time, under an advisory lock on a file beside it (`_Exclusive` from
  `model_admin`, :67, used at :570). Its own audit table is `map_admin_audit` (:265-275), behind `MapAdminAudit` (:248).
  The same module is the command line (`python -m services.api.map_admin …`, what `ospreyflow map …` runs). The routes
  are behind `manage_geospatial` (`services/api/app.py:9735`, `GET /v1/admin/maps` at :9764). The volume is rendered at
  `harness/render.py:1251` and :1410, **backed up** (`harness/backup.py:907`, `harness/cloud_platform_backups.py:341`)
  and **restored** (`harness/restore.py:723-725`).
- **The right.** `ADMINISTER_SYSTEM`, `OspreyFlow_Core/packages/schemas/rights.py:94`, in the `ADMIN` bundle
  (:125-130) and `ADMINISTRATION_RIGHTS` (:175-178).
- **Not anywhere today:** `GET /v1/appearance` or any appearance or themes route in `services/api`; an appearance
  settings module or file; a logo setting; a Themes entry in `apps/workspace/src/admin/sections.json` (its "coming"
  entries are Approval rights, :32-33, and Uploads, :34-35, both under `administer_system`); an appearance audit.
  The general audit writer is `AuditWriter.record` (`services/api/audit.py:251`).
- **Not on the server:** `ASSUMPTIONS_AND_QUESTIONS.md` (decision 14 cites its questions 24 and 25). This paper uses
  decision 14's own words for question 25: "how the Keycloak sign-in page, rendered at install, would pick up a change
  made in Admin".

## The decision proposed (each point is a question below; the proposal is (a) in each)

1. Themes settings are changed by **`administer_system` alone**.
2. They are kept in **`appearance.yaml` in a new Conduit volume `appearance-settings`**, mode `600`, written atomically
   under a lock. The first change made in Admin writes it, and from then on it **replaces `osprey.yaml`'s
   `appearance:` keys whole, except `brand` and `govuk_identity`**. It is backed up and restored as `maps.yaml` is.
3. **`brand` and `govuk_identity` stay deployment settings**, changed only by a re-render. Admin shows both as read-only
   facts.
4. **The logo is kept beside the file** (`appearance-logo.png` or `.svg`) and is checked when it is uploaded.
5. **The wider list** (Amendment 1 point 4) is typed data with fixed limits, drawn only through the trees' own macros.
6. **Everyone reads the settings through `GET /v1/appearance`**, before sign-in as well as after. It carries the
   presentational keys only.
7. **The sign-in page follows at the next re-render**, and Admin says so in words.
8. **Every change is audited** with who made it, what changed and the logo's digest.
9. **`ospreyflow check` says when the file overrides `osprey.yaml`.** A `reset` puts `osprey.yaml` back in charge.

## Questions for the owner (the proposal first)

1. **Who may change them.** (a) **`administer_system` alone, as decision 14 says** (A1, `rights.py:94`): no new right,
   and every route says so in a test that is red with the `require_right` removed. (b) A new right,
   `manage_appearance`, in the Admin bundle, so a department can let a communications officer change wording without
   system administration. Choosing (b) adds a right to `rights.py`, the roles catalogue and the Help page's words (HP),
   so it is a bigger change.
2. **Where they are kept.** (a) **`appearance.yaml`, mode `600`, in a new volume of its own (`appearance-settings`)**,
   on the Maps pattern: atomic write, an advisory lock beside it, a re-read under the lock before each change, backed
   up and restored with the Conduit's settings. (b) The same file in the existing `map-settings` volume, which saves a
   volume but mixes two owners' files. (c) A Postgres table, which is backed up with the database but is a second way of
   keeping settings that the Maps pattern does not use. **Also in (a): whole replacement, as Maps does.** After the
   first Admin change, the file holds every Themes key and `osprey.yaml`'s other `appearance:` keys are not read. The
   alternative, a key-by-key overlay, makes "which value is in force" depend on two files at once.
3. **The identity switch and the brand.** (a) **Both stay deployment settings.** Admin shows them as facts: "The GOV.UK
   identity is off. It is changed when the deployment is set up again." Neither is in the file or the `PUT` body, and
   a `PUT` that names either is refused in words. The reason: `govuk_identity` decides at build time whether the
   workspace image holds GDS Transport and the crown (`Dockerfile:59`, `sync_govuk_assets.mjs:13`). If it changed in
   Admin, the pages would either ask for a font the image lacks (a broken header) or need the font in every image
   (which breaks PL7c's "a default build holds no GDS Transport file"). (b) As decision 14 is written: the switch in
   the menu, which needs every GOV.UK image to carry the font and the crown so that turning the switch on works without
   a rebuild. That reverses PL7c for GOV.UK images. **This contradicts decision 14's list, so if (a) is chosen, the
   amendment says so and decision 14's menu loses the switch.**
4. **The logo.** (a) **PNG or SVG, at most 256 KB and 2,000 by 2,000 pixels, stored beside the file.** An SVG is refused
   if it holds a `script` element, an `on…` attribute, a `foreignObject`, or any `href` that is not a same-document
   fragment. The logo is served from the deployment's own origin at a fixed path, with `X-Content-Type-Options:
   nosniff` and a policy of its own (`default-src 'none'; style-src 'unsafe-inline'; sandbox`), and is drawn only as
   `<img>`. (b) PNG only: SVG checking has a large surface, and PNG covers every department's need at the cost of
   sharpness when scaled. The limits are mine. Decision 14 and X8 say only "PNG or SVG ... over the limit is refused".
5. **The wider list (Amendment 1 point 4).** (a) **Typed and bounded:**
   - header links and footer links, each at most 8, each with text of at most 60 characters and an address that is a
     same-origin path or `https://` (anything else is refused in words: `javascript:`, `data:`, `http:`);
   - "standard wording": named slots only, each of at most 500 characters of plain text, with no markup and no
     template syntax. The slots are the banner's words (already 200), a footer statement, and the sign-in page's
     sentence;
   - statement links: accessibility statement, privacy notice and cookies, each an address under the same rule.

   Every value is drawn through the trees' own macros with escaping, never as markup. (b) Free-form footer HTML, which
   the owner's "never templates" rule (Amendment 1 point 4) already rules out. It is listed only to be refused.
   **Which slots "standard wording" means is the owner's to name**, because the amendment does not list them.
6. **Who reads them, and how.** (a) **`GET /v1/appearance`, with no sign-in**, answering exactly the presentational
   keys (a fixed list in the test) and the logo's address and digest. It never answers the file's path, the audit or
   who changed it. The page service reads it on the server for each render, cached for at most 30 seconds. The React
   workspace reads it in place of `/deployment.json`'s `appearance` section, and `/deployment.json` keeps the section
   until both front ends read the route. (b) The page service reads the file directly. That is not allowed:
   decision 5 makes the Conduit the only way in, and the volume is the Conduit's.
7. **The sign-in page (decision 14's open question 25).** (a) **A change reaches the sign-in page at the next re-render**
   (`ospreyflow start`). The renderer reads the appearance through the Conduit's command line in the running container,
   as `ospreyflow map` does. Admin says in words next to the Save button: "The sign-in page shows this after the
   deployment is next restarted." (b) The sign-in page fetches `/v1/appearance` at load. It lives on the `id.` name, so
   this is a cross-origin read, a change to the Keycloak theme's policy and a dependency of sign-in on the Conduit
   being up. Not proposed.
8. **The audit.** (a) **The general audit (`AuditWriter.record`, `audit.py:251`)**, with actions `appearance_changed` and
   `appearance_logo_changed` (and `appearance_reset`). A row holds who, when, the keys changed with their old and new
   values, and the logo's SHA-256, never its bytes. (b) A table of its own like `map_admin_audit`. That is consistent
   with Maps, but it is a second audit place for a reader to look in.
9. **When the file overrides `osprey.yaml`.** (a) **`ospreyflow check` says so in words** when the file exists and
   `osprey.yaml`'s `appearance:` (other than `brand` and `govuk_identity`) differs from it ("osprey.yaml's appearance is
   not in force: Admin › Themes changed it on <day>"). `python -m services.api.appearance_admin reset --by <who>`,
   audited, removes the file so `osprey.yaml` is in force again. (b) Say nothing. An operator would then edit
   `osprey.yaml` and see no change, and nothing would tell them why.
10. **The first slice.** (a) **AD4a: the Conduit half only, with no screen.** It builds the store, `GET` and `PUT
    /v1/appearance` (the `PUT` behind `administer_system`), the logo upload and serving, the audit, the command line,
    backup and restore, and `ospreyflow check`'s sentence, each with its access-control test written first (rule 4).
    After it: AD4b, the GOV.UK tree's *Admin › Themes* page (a form, scripts off); AD4c, both front ends reading
    `/v1/appearance` and the GOV.UK layout drawing the settings; AD4d, the React workspace's Admin section, if the owner
    wants one on the default theme. (b) One slice with the GOV.UK page, which is too big for the dial's rounds.

## The table of cases (each red first; planted faults at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | `PUT /v1/appearance` by a person without `administer_system` | refused, as every Admin route refuses; nothing written; no audit row | the route's `require_right` removed (X8's `test_only_a_holder_of_administer_system_changes_the_appearance`) |
| 2 | `GET /v1/appearance` with no session | exactly the presentational keys, in a fixed list | the whole file returned (X8's `test_the_public_appearance_read_carries_only_the_presentational_settings`), written with the wider list's keys (Amendment 1 point 4) |
| 3 | A `PUT` naming `brand` | refused in words; the brand is unchanged | the key let through to the file (X8's `test_the_brand_cannot_be_changed_through_the_themes_route`) |
| 4 | A `PUT` naming `govuk_identity` (if question 3 is (a)) | refused in words, saying it is changed by setting the deployment up again | the key let through |
| 5 | A logo that is not PNG or SVG, is over the limit, or is an SVG with a script, `on…`, `foreignObject` or outside `href` | refused in words naming the reason; the old logo stays | each check removed in turn; an SVG with `onload` in an attribute of a nested element, the shape a real upload would take |
| 6 | The logo served | own origin, `nosniff`, its own policy, the right content type | the header dropped (X8's `test_the_logo_is_served_with_nosniff_and_a_policy_of_its_own`) |
| 7 | Every change | one audit row with who, when, keys old and new, the logo's digest, never its bytes | the audit call removed; the logo bytes written into the row (X8's `test_every_appearance_change_is_audited_with_who_made_it`) |
| 8 | Two changes at once (two replicas, or Admin and the command line) | both applied one after the other, each on the file as the other left it; neither lost | the lock removed (shown by two writers interleaved by the test, not by chance: as PL4d3f forced its race) |
| 9 | The first Admin change | the file is written with every Themes key; from then on `osprey.yaml`'s Themes keys are not read; `brand` and `govuk_identity` still come from `osprey.yaml` | an overlay instead of a whole replacement (a key left out of the file falls back to `osprey.yaml`) |
| 10 | The file's mode and the write | `600`, written atomically (a crash mid-write leaves the old file whole) | `0o644`; a write that is not atomic |
| 11 | A link that is `javascript:`, `data:`, `http:` or longer than its limit; wording with markup | refused in words; nothing written | each check removed |
| 12 | Backup then restore | the file and the logo come back byte for byte | the volume left out of `backup.py` |
| 13 | `ospreyflow check` with the file present and `osprey.yaml` different | the sentence of question 9 | the comparison removed |
| 14 | `reset` | the file removed, audited, `osprey.yaml` in force again | the audit call removed |
| 15 | An unauthorised reader cannot learn from `GET /v1/appearance` who changed it or when | no person and no time in the answer | the audit's last row added to the answer |

## Checks (for AD4a; frozen when it is cut)

The new Conduit tests (pure, stores at the conformance fakes, ports pinned to 9); `tests/harness/` tests for backup,
restore and `check`; `tests/services/api/test_rights_table*` (the route in the rights table); the decision log's own
checks (`decision_log_publication_check.py`, the reservation check) on the amendment; `tests/test_doc_citations_check.py`;
`ruff check .`; `mypy` as the Conduit's checks run it; the scan-map check for each new test file; the cheap checks of
20 November (ruff and eslint on every file touched).

## Out of scope

The `brand` setting (it stays a deployment setting: decision 14); `govuk_identity` in Admin (if question 3 is (a)); a
department's uploaded template (never: Amendment 1 point 4); the GOV.UK page and the workspace section (AD4b, AD4d);
the sign-in page reading the Conduit live; any change to `osprey.yaml`'s schema other than the logo and the wider
list's keys; the GOV.UK demo's settings (nothing changes the running deployment without the owner's word).
