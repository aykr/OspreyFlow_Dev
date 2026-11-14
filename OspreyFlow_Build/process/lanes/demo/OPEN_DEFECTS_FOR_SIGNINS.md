# Open defects a user could see, for the owner before client sign-ins

From the orchestrator, 14 November 2026, evening, collected from every lane's list (each lane checked its own) and
held to main at 10ff9e2 or later. The owner gives client sign-ins on the GOV.UK demo only once this list is empty or
each item is accepted. **Every fix the candidate carries is not here**: those are merged (route rows T to S9, M9).

Column "On the demo?" says whether a visitor to osprey-small (local Small, Keycloak, analyst-level Demo visitor role,
their own case over the shared demo data) could meet it.

## A. A demo visitor could meet these

| # | What the user sees | Where | On the demo? | Owner | Fixed? |
| --- | --- | --- | --- | --- | --- |
| A1 | Opening *More views* hides the case line beneath it ("· Views in this case ·", at narrower widths the Ingest Studio link and the case selector's edge) until the menu closes; the GOV.UK header and the marking are never covered | the top bar's More views, all widths (rules measured 1440/1024/924, GOV.UK) | yes | case | open (CARRIES 97) |
| A2 | Alert sources shows a hotlist's or watch's *Stopped* with no reason, where Hotlists and Watches on the same tab say why | AlertSourcesPanel.tsx, alert_sources.py | yes, if a visitor's case has a stopped watch | rules | open (CARRIES 245) |
| A3 | The case's Alerts panel reads the whole active queue to show its newest five, so it is slow on a large queue | reports/api.ts fetchNewestAlerts | rarely: the demo's queue is small | rules | open (CARRIES 43) |
| A4 | Needs you's fallback for an older schedule notice names no pipeline ("A scheduled load of yours did not run as planned…") | schedule_notices.py:56–65 | only with old notices; a visitor has none | rules | open (CARRIES 129) |
| A5 | The guides' screenshots show the navigation before ADR-145 Amendment 15 (five in the user guide, Schedules and runs in the admin guide) | docs/images | yes, if a visitor reads the guide | docs | after the cut, on the owner's word (sweep §10) |
| A6 | Mark for suppression records a mark and its reason and hides nothing yet (R7 step 2 is not built) | the node menu | yes; the menu says "(hides nothing yet)" | — | accepted (the owner, R7) |
| A7 | Search, by design: a merged entity on two pages; a Document in two groups; no matched field on a typo match; the fallback's "counts may be higher, no date filter"; a just-changed record missing while the index catches up (M6: 2.8 s) | the search results page | yes | — | accepted (the owner, ADR-149) |
| A8 | A batch job whose worker dies shows "running" for its 10 minutes plus one | the batch panel | unlikely | — | accepted (ADR-151 Cost) |

## B. Not on the demo (Entra, cloud-platform, operators or the scheduler)

| # | What the user sees | Where | Owner | Fixed? |
| --- | --- | --- | --- | --- |
| B1 | An identity-provider outage counts as the schedule owner refusing: a scheduled pipeline or watch is paused with a refusal's words, not "not reached" | principal_auth → scheduler (CARRIES 136) | rules | open |
| B2 | A store fault while acting as the owner leaves no notice or ledger row; the slot later reads "missed — the deployment was not running then", and a watched file's claim is held a week | scheduler.py _consider_slot/_consider_watch (CARRIES 137) | rules | open |
| B3 | An owner on two screening lists raises two alerts and two owner_listed factors | KYC rules (CARRIES 114), a spec question for ADR-146 | rules + a ruling | open |
| B4 | A pattern rule or AML/KYC template made live runs "just for me", not case-wide | rules' make-live (CARRIES 88, 93) | rules | open |
| B5 | Admin › Operations and the owner refusals name an owner by account id, not their name | Admin (visitors hold no Admin) | admin | carried after v0.5.2 |
| B6 | On Entra, people's names can show as object ids where ADR-106's directory is read | Entra only | admin | carried |
| B7 | A SQL or API connection on a port not installed times out with no warning | Admin › Connections, cloud-platform | admin | carried |
| B8 | A transfer or promotion refused as stale tells the person to sign in again, where the fix is an administrator setting the value | Entra, Admin › People | platform-b | carried (needs a schema field) |
| B9 | Demo accounts removed in Admin › People come back after repair-sign-in, start --build or a restore; after a restore nobody has a password | the demo's sign-in | platform | Part 3, after the cut; the owner's steps remove visitors in Admin › People, never by restore |
| B10 | govuk.ospreyflow.app's certificate does not renew itself (expires 10 Feb 2027) | the whole site | platform | Part 3, needs the registrar's keys |
| B11 | On a ClickHouse deployment the public seeds' events go to a DuckDB file, so their timelines show nothing | ClickHouse deployments (not the demo) | platform | partly fixed for the POC's seeders |
| B12 | Operator-only: cloud-platform INSTALL.md step 6 doesn't run helm upgrade; a mail: section asks for unused networks; a refusal names the build step "P10"; Admin › Models' refusals leave out helm upgrade | cloud-platform | platform, platform-b | carried |
| B13 | A Studio SQL step past its time limit while its rows are read shows a raw "OSError: INTERRUPT" | the Ingest Studio's expert SQL | studio | fix held for the owner's word (lane/studio-sql-interrupt 345c457) |
