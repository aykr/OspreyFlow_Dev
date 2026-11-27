# Slice GR1f2 · GR1 · Changing who can open a case, as scripts-off forms: give a level, change it, take it away, and the unit-wide level (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M** (about 14 cases). GR1f's second part, on GR1f1's settings page.

**Where it comes from.** ADR-052 §4 and §5 (`spec/06` about lines 7242 to 7251): "A case's Authors manage its access";
"Every change of access is recorded in the case's history"; the unit-wide level "An Author may set to none, viewer or
editor". `spec/03` §3's Author row (`spec/03_CONDUIT_MIDDLEWARE.md:384`): `access` (PUT: the unit-wide level, "never
Author"), `access/grants/{account}` (PUT, DELETE). The React Share panel
(`apps/workspace/src/investigation/CaseAccessPanel.tsx`, `access.ts`), which gives and removes grants and **does not
offer the unit-wide level**. The write pattern is the page service's own: a `POST` with `_csrf`, the Conduit called by
the server half, then a `303` to a `GET` (GG4c's, as cut; GR1d's on `away/GR1d`).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`services/api/app.py`), each `require_right(SHARE_CASE)` and `InvestigationAccessManagerDep` (the
  Author, or the administrator's safety net, :3033-3036):
  - `PUT .../access/grants/{account_id}` (`set_investigation_grant`, :4700-4724), body `GrantInput` `{level}` (:4625-4626),
    `204`. The account id is checked by `_grantee` (:4629-4639): trimmed, 1 to 200 characters, else **422** with a
    plain-string detail. Then `_may_hold_a_level` (:4642-4697): a `team:<role id>` that does not exist is **409
    `no_such_team`**, its message naming the role id after `team:` (:4651-4661); a dashboard identity above Viewer, or
    (with a directory) anything that is not an enabled person, is **409 `service_account`**, its message naming the
    account typed (:4677-4697). The store upserts the grant, so the
    same `PUT` **changes** a held level (`services/api/investigations.py:405-418`). Audited `grant_access`.
  - `DELETE .../access/grants/{account_id}` (:4727-4747), `204`, audited `revoke_access`. **It succeeds for an id that
    holds no grant** (the store's `DELETE` matches nothing and still records a revoke, `investigations.py:420-427`).
  - `PUT .../access` (`set_investigation_unit_level`, :4602-4622), body `UnitLevelInput` `{unit_level: "viewer" |
    "editor" | null}` (:4595-4599), `204`, audited `set_unit_level`.
  - Refusals before the body: the right's **403**, a level below Author **403** (`_authorize`, :2944-2946), no level
    **404** (`InvestigationNotFoundError`).
- **No Conduit guard keeps an Author.** Nothing in the routes refuses removing or lowering the last Author grant:
  ADR-052 §4's safety net (an administrator of the case's unit) is what rescues such a case. Authorship is an ordinary
  grant row (`_LEVEL_SQL`, `investigations.py:110-118`). **The React panel does keep one**: it offers no Remove for the
  last Author ("The last Author stays: removing them would leave nobody to manage the case",
  `apps/workspace/src/investigation/CaseAccessPanel.tsx:76-78`, :86).
- **A slash in a path part.** GR1a found that the Conduit's server decodes `%2F` before its router sees the path
  (`apps/pages/server/cases.ts:63-67`), so an account id holding `/`, or one that is `.` or `..`, would ask another
  route.
- **The React words**: `refusal()` (`access.ts:27-32`) says 403, 404 and 422, and nothing for the two 409s.

## Acceptance (red before, green after)

Scenario CS's access rows, written first after GR1f1's; `apps/pages/test/govuk/case-access.test.ts`, red on GR1f1's
page, green after; GR1f1's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Give a level to an account, change a held level, take one away, and set the unit-wide level**: every
   access route the spec names as the Author's. (b) Grants only, as the React panel: the unit-wide level left to the
   React workspace, which does not offer it either.
2. **Who is offered the forms.** (a) **The Author holding `share_case`** (the React rule, `canChangeCase`,
   `apps/workspace/src/rights/visibility.ts:83-90`), read from the listing's level and `GET /v1/me/rights`; anyone else
   sees GR1f1's read-only part, and a hand post is said in the page's words. (b) Offered to every reader, the route
   refusing: not proposed.
3. **Naming the account.** (a) **One text field, "Account id, as the Admin area shows it"** (the React hint,
   `CaseAccessPanel.tsx:122`), with "a team is written `team:` and its id" beneath; no list of people or teams (no route
   a case Author may call lists them). The page refuses before any call an empty id, one over 200 characters, `.`,
   `..` and one holding `/`, each said beside the field. (b) A list of the unit's people: needs a directory read the
   Author does not hold (a widening, and the owner's).
4. **The level offered.** (a) **Radios Viewer, Editor, Author**, as the route takes all three for a grant; the
   unit-wide level's radios are **No one else, Viewer, Editor** (the route takes no Author, `app.py:4595-4599`). (b)
   Author left out of the grant form: narrower than the route and the React panel.
5. **Taking away a level.** (a) **A confirmation step drawn by a `POST`** (the account in a hidden field, never in the
   address, since an account id may be a person's sign-in name), saying "<name or id> will no longer be able to open
   this case through this grant. They may still open it through your unit's level or a team."; its button sends one
   `DELETE`. (b) A `GET` asking page with the account in the query, as GR1d's `&delete=<view>`: puts a person's id in
   the address bar, the history and the server log.
6. **The last Author grant (owner: access control).** (a) **The React panel's rule: no Remove and no lower level is
   offered for the last Author grant in `grants`** (`CaseAccessPanel.tsx:76-78`), with the sentence "The last Author
   stays: removing them would leave nobody to manage the case."; a hand post is still sent, since the route allows it.
   Taking away or lowering one's own Author grant while another Author is left is offered, with one more sentence on
   the confirmation: "You will no longer be able to change who can open this case." The page counts nothing it shows
   as a figure; it only decides what to offer from what the Author was sent. (b) Offered, with a warning, as the route
   allows it: a departure from the React parity. (c) A Conduit guard refusing the last Author's removal: an ADR-052 §4
   change and an amendment (decision 11).
7. **Refusals in words.** (a) **Each has the page's own sentence**: 422 "An account id is 1 to 200 characters." (the
   field's error); 409 `no_such_team` "There is no team with that id." (the Conduit's message names the role id); 409 `service_account` "That account cannot
   hold this level: a dashboard can be a Viewer and nothing more, and a service account or a disabled account holds
   no level."; a 403 on a hand post "Only the case's Author can change who can open it."; an unknown code "Nothing was
   changed." The Conduit's message (which repeats the typed id or role id) is never shown. (b) The Conduit's message.
8. **After a change.** (a) **A `303` to the settings page with one banner**, carried in the session as GR1d's (so a
   link cannot forge it): "<name or id> can now open this case as an Editor.", "<name or id> no longer has a grant on
   this case.", "Everyone in your unit can now open this case as a Viewer." (b) No banner.
9. **A removal of an id that holds no grant** (the route answers `204`). (a) **The form only ever offers ids the
   Author was sent in `grants`**, so a hand post is the only way; its banner is the same sentence, since the route says
   nothing more. (b) A check against `grants` before the call: a read-then-write race the route does not make.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | The Author gives `a.morrow` (synthetic) Editor | one `PUT .../access/grants/a.morrow` with exactly `{"level": "editor"}`; `303`; the banner; the grant in the table | `_csrf` passed through in the body |
| 2 | The Author changes a held Viewer to Author | one `PUT` with `{"level": "author"}` | a `DELETE` then a `PUT` |
| 3 | `team:analysts`, and a team that does not exist | the team's grant; the `no_such_team` sentence, the typed id kept in the field | the 409's message shown |
| 4 | A dashboard identity asked to be Editor | the `service_account` sentence; nothing changed | the 409 drawn as "could not be read" |
| 5 | An empty id, 201 characters, `.`, `..`, `x/../access` | each said beside the field; **nothing asked** | the id sent encoded (`%2F`), reaching another route |
| 6 | Take away a grant | the confirmation drawn by a `POST`, with no write; its button sends one `DELETE`; the banner | the confirmation's first button sending the `DELETE` |
| 7 | The account in the address | never: no `GET` address on the page holds an account id | the asking step written as a `GET` with `account=` |
| 8 | The Author takes away their own grant with another Author left; and the last Author grant | the first: the extra sentence on the confirmation, then the `DELETE`; the last: no Remove and no lower level offered, "The last Author stays…" said | the last Author's Remove offered (the React parity broken); the Author count taken from anything but `grants` |
| 9 | The unit-wide level set to Editor, then to No one else | one `PUT .../access` with `{"unit_level": "editor"}`, then `{"unit_level": null}` | `"none"` sent as a string (the route's `Literal` refuses it) |
| 10 | An Editor with `share_case` posts each form by hand | the 403's sentence, nothing changed | the 403 passed through |
| 11 | No level, another unit, no case, posted by hand | GR1a's 404 page | the 404 said as a refusal of the change |
| 12 | No `_csrf`, an empty one, a wrong one | refused, nothing sent (I17) | the form outside the check |
| 13 | The fixture | refuses as the routes do, in their order (the right, the level, `_grantee`, `_may_hold_a_level`), and keeps the upsert | a fixture that refuses a second `PUT` for the same account |
| 14 | Keyboard and scripts off | each form and each confirmation reachable and working, one keyboard case per action (rule 13) | a confirmation button out of the tab order |

## Waits on

GR1f1 merged (the settings page); GR1d merged (the page's write pattern: `POST` with `_csrf`, a `303`, the banner in the
session).

## Files touched

`spec/08` (CS's access rows); `apps/pages/server/cases.ts`, the settings words (GR1f1's file); `tree-govuk/case-settings.njk`
and an access-confirmation partial; `test/govuk/case-access.test.ts`, `casesConduit.ts`, `keyboard/cases.spec.ts`,
`scripts-off/cases.spec.ts`; the scenario test's input census (`GrantInput`, `UnitLevelInput`).

## Checks (frozen when cut)

GR1f1's list, with `test/server/csrf.test.ts` over the new `POST`s.

## Out of scope

The access history (GR1f1 question 7); a people or team picker (question 3); the administrator's safety net; a
last-Author guard (question 6 (b), the owner's); any Conduit change; `apps/workspace` (whose `refusal()` says neither
409: a note for a later React part).
