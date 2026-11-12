# Platform-b lane · brief gate-b · a disclaimer banner and a shared-key prompt for the demo, by Friday morning (S)

Written by the orchestrator, 12 November 2026 late evening, at the owner's request, for the platform-b session on
`sol`, from **main** (branch `lane/platform-b-gate` from `main`). Your CI step is done (its brief is
BRIEF_ci_diag.md); stay alert for its GitHub result. Opus, medium. Size S. **Deadline: merged by 08:30 UK on Friday
13 November**, so the demo lane can deploy it to osprey-small by 10:00.

**The owner's decision (12 Nov, about 23:15):**
1. **A disclaimer on every screen.** The GOV.UK phase banner's text, fixed today ("This is a new service",
   apps/workspace/src/…/PhaseBanner.tsx:14, as PART2.md §4 found), becomes settable in osprey.yaml, for example
   `appearance.banner_text`. The owner's wording, used on osprey-small: **"Demonstration only: this is not a
   government service, and all data is synthetic."** It shows in the Glass and on the sign-in page (Keycloak's
   GOV.UK chrome, harness/keycloak_theme.py). With phase `none` and banner text set, the banner shows that text alone.
   Unset, nothing changes for any deployment. **ADR-132 Amendment 7, reserved for you.**
2. **A shared-key prompt before anything loads.** The product's own proxy (Caddy, rendered by harness/site.py) asks
   for a shared key, the browser's built-in username and password box, on **all three names** (the app, id. and bi.),
   before any page, asset, sign-in or API answer. It is checked on the server against a **bcrypt hash only**, which the
   owner sets on the server (a setting such as `server.access_key_hash`, or a root-only file that the render reads;
   choose the strict option). The key itself is never in osprey.yaml, the repository, a message or a log. Unset, no
   prompt and nothing changes. Add `X-Robots-Tag: noindex` on every response when it is set. Mind the paths that must
   still work behind it: Keycloak's sign-in and token endpoints, the Glass's own fetches, Superset's OAuth callback.
   Basic auth sends the key on every request, so it must only ever travel over TLS. **ADR-114 Amendment 41, reserved
   for you.**
3. A small CLI or harness helper the owner runs on the server to set the key: it reads the key twice without echo,
   writes only its bcrypt hash where the render reads it (mode 600), and says to run `ospreyflow apply`.

**Rules:** each piece red first (rule 15): the banner's text, the prompt refusing without the key and with a wrong
one, every path covered on all three names, the hash never logged, and nothing changing when unset (byte-for-byte
renders of every profile and fixture, cp-policy-check included). An access-control test (rule 4) for the prompt on
each name. Keyboard and axe for the banner in three themes. The generated types if packages/schemas changes (its own
commit at the head). One lane-reviewer round. Gates on the Mac, and on the server **only before 11:30 Friday** with
my word: rules has the heavy slot tonight. Then "ready".

**Never.** osprey-small is the demo lane's: you never touch it. No key, hash or password in any message, file you
commit or log. No push.
