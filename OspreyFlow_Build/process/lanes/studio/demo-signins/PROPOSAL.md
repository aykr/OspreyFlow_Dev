# Demo sign-ins for visitors: a proposal

The studio lane, 14 November 2026, for the orchestrator (due Sun 15 evening). Read from main at
`fe69379`. Every claim about the code cites the file and line it was read from; nothing here was
read from or run on osprey-small, the owner's demo deployment, and no password or code appears
here.

The question: how a visitor gets a sign-in of their own to a demo deployment, sees only what they
should, cannot become an administrator, and spends the hosted model (Gemini) without running up the
owner's bill or meeting a screen that hangs.

## In one paragraph

A demo with visitor sign-ins is a **Small** with ordinary accounts made in *Admin › People*, one
case per visitor, granted at **Editor**, under a **custom role** that is the analyst's rights
without making, sharing or removing cases, and without export. All of that can be done today, by
hand, with no code. Three things cannot, and are proposed as builds:
1. a server-side refusal of the Admin role for people made by anyone short of `administer_system`;
2. words for the hosted model's own refusals and time-outs, which today read as a fault or a hang;
3. a reset that keeps visitors able to sign in.

A per-person model allowance is not possible without an ADR-135 amendment and is left to the
owner.

## 1. Which deployment

- The shared access key, the one gate in front of a deployment's sign-in page, is refused on any
  profile but Small (`OspreyFlow_Core/packages/schemas/deployment.py:2168-2177`). It is one key
  for everyone, written as a single user and bcrypt hash into the front proxy's snippet
  (`OspreyFlow_Core/harness/access_key.py:71-77`). So it keeps strangers off the sign-in page,
  but it is not a per-visitor credential: each visitor still needs a sign-in of their own.
- **Proposed:** the demo is a Small with `network.access_key` set, and one account per visitor
  behind it. The key is given to every visitor alike. Their own account is what tells them apart
  in the audit, in case grants and in model usage.

## 2. Making a visitor's account

What exists:
- *Admin › People*'s invite creates the Keycloak user with `requiredActions: ["UPDATE_PASSWORD"]`
  (`OspreyFlow_Core/services/api/identity_admin.py:428-436`).
- With no email delivery, it sets a temporary credential to a generated one-time code
  (`identity_admin.py:439-442`): sixteen letters, 80 bits, from an alphabet with no 0/O or 1/I
  (`identity_admin.py:124-132`).
- The browser shows the code once, with the words "Give this one-time code to … in person. It is
  shown once, here; at first sign-in they choose their own password"
  (`OspreyFlow_Core/apps/workspace/src/admin/sections/People.tsx:128-130`).
- So the owner never chooses or types a visitor's password, and the visitor sets their own at
  first sign-in. That meets "no password or access code printed, logged or written by our tools":
  the code is on screen once, nowhere else.

What a visitor's account needs so that they see anything, all of it set on the same invite form:
- their organisational unit;
- clearance OFFICIAL;
- the handling code(s) the demo data carries (P for the shipped packs);
- a grant on their case (§3).

What is missing:
- **Nothing stops a visitor being made an Admin.** The form offers `osprey-admin` among the
  built-in roles (`People.tsx:48-54`), and the server's `allowed_role` admits any built-in,
  legacy, custom or single-right role (`identity_admin.py:140-147`), checking which role it is
  but not who is giving it.
  - The administration rights do have a giver check for custom roles and single rights
    (`OspreyFlow_Core/packages/schemas/rights.py`, `ADMINISTRATION_RIGHTS`, "a custom role may
    hold one, and a person be given one, only by someone who holds it").
  - The built-in `osprey-admin` passes `allowed_role` without it.
  - **Build A (small):** refuse the `osprey-admin` role, at the route, to a giver without
    `administer_system`, with a test that a `manage_people`-only giver is refused (rule 12).
    Whether that is the rule the owner wants, or only "never on a demo", is the owner's call.
- **There is no command to add a person.** A run of visitors is made one by one in the browser.
  - **Build B (optional):** a harness command that makes one visitor with fixed attributes (the
    demo role, OFFICIAL, P, the unit) and shows the one-time code once on the terminal, never
    in a file or log. Worth building only if the owner expects more than a handful of visitors
    per demo.

## 3. Keeping visitors apart

What exists:
- A case grant is Viewer, Editor or Author, each including the one below
  (`OspreyFlow_Core/services/api/investigations.py:120-133`).
- Changing a case's datasets needs Author (`OspreyFlow_Core/services/api/app.py:4130`), and so
  does managing its access (`app.py:2865-2867`). An Editor can work in the case but cannot add
  another dataset to it or share it.
- A new case is made with no unit-wide level (`investigations.py:279-281` leaves `unit_level`
  unset; only the one-off migration of older cases set it to viewer, `investigations.py:91-95`).
  So visitors in one unit do not see each other's cases unless someone sets it.

**Proposed:** the owner makes one case per visitor, with the demo dataset, and grants the visitor
Editor on it, not Author.

The gap: an analyst can make a case of their own.
- Case creation needs only the `create_case` right (`app.py:4022-4026`), and whoever creates a
  case is its first Author (`app.py:4035`). The analyst role holds `create_case`, `share_case`,
  `remove_case`, `export` and `export_override` (`OspreyFlow_Core/packages/schemas/rights.py:106-114`).
- So a visitor given the Analyst role could make a case, become its Author and add any dataset
  their unit and markings already let them read.
- **Proposed, with no code:** a custom role, *Demo visitor*, made in *Admin › Roles*
  (`app.py:16952-17006`; ADR-112 Amendment 4). It is the analyst's rights without `create_case`,
  `share_case`, `remove_case`, `export` and `export_override`, and the visitor is given that role
  rather than Analyst.

A caveat for the owner: an Editor's writes to the graph (an added node, a confirmed link) land in
the dataset the case reads. If two visitors' cases read the same demo dataset, each can see what
the other wrote there. One dataset copy per visitor would close that, at the cost of a load per
visitor.

## 4. Resetting between demos

What exists:
- A backup's identity item carries every person with their id, attributes and roles
  (`OspreyFlow_Core/harness/backup.py:475-504`, `OspreyFlow_Core/harness/identity.py:82-104`);
  Keycloak's own database is not dumped (`backup.py:382-389`).
- **Passwords never travel**: Keycloak does not give them out, and only the install's own demo
  accounts are given theirs again (`identity.py:21-23`).

So:
- **Restore from a backup taken before the visitors existed:** their cases and data go. Their
  accounts survive only if Keycloak's realm is not wiped, so a restore is not a clean reset of
  the people.
- **Restore from a backup taken after they existed:** their accounts come back with their ids,
  but with no password. Each visitor needs a fresh one-time code (*Admin › People*'s reset)
  before they can sign in again.
- There is no scheduled reset of any kind.

**Proposed:**
- Remove visitors in *Admin › People* at the end of a demo, rather than restoring.
- Treat a restore as data-only. Its words say "people need a new code after a restore"; the
  restore's report should say so if it does not already. Verifying that against the restore
  verb is **Build C**, a check, not yet a change.
- CARRIES row "Demo accounts and resets for public demos" (platform, Part 3) already holds the
  related gap: the install's own demo accounts are made again by repair, start and restore while
  `deployment.env` holds `OSPREY_DEMO_*_PASSWORD` (`OspreyFlow_Core/harness/apply.py:1455-1475`).
  Visitors should never be given those accounts.

## 5. Gemini: cost and what a visitor sees

What exists:
- Each hosted engine has one gateway key, with a request, token and budget limit set in
  *Admin › Models* (`OspreyFlow_Core/services/api/model_admin.py:326-339`).
  - The budget is per engine and shared by everyone who uses it.
  - No call carries a person's id (`OspreyFlow_Core/packages/adapters/model_litellm/client.py:36`,
    ADR-135 Amendment 3). So the gateway cannot hold one visitor to a share of it.
- When the engine's own budget or rate limit is reached, the gateway's refusal becomes
  `ModelLimitReached` (`OspreyFlow_Core/packages/adapters/model_litellm/usage.py:107-135`). Its
  words say which limit and when it resets
  (`OspreyFlow_Core/packages/adapters/model_litellm/errors.py:69-76`), and the Conduit gives them
  (`app.py:3756`).

The gaps, each a visitor could meet:
- **Gemini's own refusal reads as a malformed answer.** `limit_refusal` recognises only the
  gateway's limits: "a cooldown's 429, a provider's own 429 passed through" returns None
  (`usage.py:108-110`).
  - Any other 4xx stops the retries (`client.py:162-163`) and becomes `ExtractionFailedError`
    (`client.py:166-169`).
  - The Conduit answers that 502 with "The model answered, but not in the shape asked for"
    (`app.py:3323-3331`).
  - So Gemini's own quota (429) or a bad key (401) is shown to the visitor as the model
    misbehaving, and to the owner as nothing actionable.
- **A slow answer has no deadline the visitor can see.**
  - The model client waits up to 900 s by default (`client.py:80`, `OSPREY_MODEL_TIMEOUT_SECONDS`
    at `client.py:92`). A timeout is not caught in the retry loop (`client.py:140-163` catches
    only decode, validation and HTTP status errors), so it surfaces as an unhandled 500.
  - The Glass's calls to the model routes set no deadline or abort signal:
    `apps/workspace/src/patterns/api.ts:112-116` and `apps/workspace/src/reader/readerApi.ts:57-61`.
  - So a visitor watches a spinner for up to fifteen minutes and then reads a generic fault.

**Build D (recommended before any public demo):**
- In the client, map a provider's 429 and 401/403 to their own errors, and an `httpx`
  time-out to a `ModelTimedOut`.
- Give each its own words in the Conduit: "the hosted model is refusing more requests just
  now", "the hosted model's key was refused; tell your administrator", "the model took too long".
- Give the Glass's model calls a deadline shorter than the gateway's, with words of its own.
- Each needs a fake that refuses as Gemini does, built from a measured Gemini 429 and 401
  (rule 15: the fake must model the real refusal, not the happy path).

**Not proposed without the owner:** a per-visitor allowance.
- It needs each call to carry who asked, which ADR-135 Amendment 3 chose not to do, so it is an
  ADR-135 amendment.
- Until then, the owner's control is the engine's daily budget in *Admin › Models*, sized for a
  demo, with the refusal's words (above) telling visitors when it is spent.

## For the owner to decide

1. Is the *Demo visitor* custom role (§3) the shape the owner wants, or should visitors be
   Analysts on a deployment with nothing else on it?
2. Build A: refuse Admin to every giver short of `administer_system`, or only on demos?
3. Build B (a harness command per visitor): needed, or is the browser enough for the expected
   numbers?
4. One demo dataset shared by all visitors (each sees others' edits), or a copy each?
5. Build D before the next public demo: yes or no. And a per-visitor model allowance: worth an
   ADR-135 amendment?

## Builds, in the order proposed

| | Build | Size | Needs |
| --- | --- | --- | --- |
| D | Words for a provider's 429/401 and a model time-out; a Glass deadline | small–medium | a measured Gemini refusal for the fake |
| A | Refuse `osprey-admin` to a giver without `administer_system` | small | the owner's answer to 2 |
| C | Check, and if needed say, that people need new codes after a restore | small | — |
| B | A harness command that makes one visitor, code shown once | small | the owner's answer to 3 |
