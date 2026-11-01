# Alerting and monitoring as a core feature

**Status:** planned 1 November 2026, at the owner's request; nothing built yet. It runs after the
GOV.UK deck work in flight (capture, decks, merge) and before the repository move
(`REPO_MOVE_PLAN.md`), unless the owner reorders them.

**The owner's requests (1 November 2026):**
- "Event monitoring and alerting needs to be highlighted as key features, this means that the reporting
  screens should allow for this as well." The owner chose all three: alerts in report packs, a
  monitoring dashboard, and alert trends.
- "Add the use cases to illustrate alerting and monitoring to the prison Intelligence demo as well as
  the AML demo case."
- "I would also like alerting and monitoring features to be highlighted as core feature hence all the
  decks and guides will need updated."

**Already done:** ADR-115 Amendment 4 puts "event monitoring and alerting" in the product's one-line
description, as a fifth capability on the welcome page and as a part of About.

## Where the demos stand

- **Prison Intelligence:** one alerting moment, in chapter 9: a hotlist on the coordinator's number
  fires when the batch-2 seized-phone file loads. The alert names the hotlist entry, the node it
  matched, and the file and row.
- **Operation Ledger (AML):** the structuring ring raises a typology alert as it loads, and the
  onboarding file is screened before commit. Both are part of the loading story; nothing shows
  ongoing monitoring of later data.

## Stage 1 — map what is built

For each candidate use case, mark it as one of: **built today**, **needs the reporting ADR**, or **a
product gap**. The demo claims only what the product does. The facts on alerts, packs, trends and
dashboards are being gathered now.

## Stage 2 — choose the use cases (owner approval 1)

Candidates (the owner chooses):

| | Use case | Depends on |
| --- | --- | --- |
| P1 | A new PIN-phone call log arrives, and a typology rule flags a prisoner calling a number already seized from a handset | rules on load (check) |
| P2 | A hotlisted associate books a visit: the visits batch raises the alert before the visit | hotlists (built) |
| P3 | A weekly alerts trend for Wing F, and the chapter 9 alert as a pack item, in chapter 11's pack | reporting ADR |
| P4 | The monitoring dashboard: alerts raised and closed per week, and the open queue | reporting ADR |
| A1 | Next week's transactions file: rapid-movement and circular-flow rules fire | rules on load (built) |
| A2 | A new cash deposit into a hotlisted mule account raises an alert | hotlists (built) |
| A3 | A sanctions or PEP list update makes an existing customer match on re-screening | **unknown: re-screening on a list change may be a product gap** |
| A4 | An alert is closed with a reason, then appears in the case's pack and on the dashboard | reporting ADR |

## Stage 3 — decisions (owner approval 2)

1. **A proposed ADR for alerts in reporting:** a fifth pack item kind, `alert`; a monitoring dashboard
   fed through the reporting mart; and alerts as a trend series. Every count is over what the reader
   may see (rules 3, 4 and 7), and an alert's inferred match stays inferred (rule 5).
2. **ADR-127 (Prison Intelligence) and ADR-108 (Operation Ledger) amendments.** For each chosen use
   case: the data it needs, the exact alert it raises, the test that fails if it stops firing, and the
   test that fails if it fires when it should not (a hotlist added after the load, a reader without
   the dataset).

## Stage 4 — build (one worker against the tree at a time; rule 14)

1. **The reporting features**, tests written first, each with its access-control test.
2. **The demo data:**
   - new synthetic batch files generated from the existing plans (`pid_plan`, `ledger`), placed in
     `incoming/` as the demo loads them;
   - golden tests: "this batch raises exactly these alerts, in this order".
   - Rule 9 holds: synthetic and in the repository only.

## Stage 5 — make it a core feature everywhere

**Product and guides:**
- **README:** the feature list leads with monitoring and alerting beside mapping.
- **User guide:** a full chapter on monitoring and alerting:
  - hotlists and watches, with review dates;
  - typology alerts and the queue;
  - each alert's explanation;
  - closing with a reason;
  - alerts in packs, trends and the dashboard.
- **Developer guide:** writing and testing a typology rule in the Ingest Studio, and how a load
  raises alerts before commit.
- **Administration guide:** who sees alerts, the monitoring dashboard's feed, and retention.
- Each guide gets a new version and its PDF; the documentation site follows.
- `DEMO_GUIDE.md` and the Prison Intelligence setup guide get the new chapters.

**Demos:**
- the prison demo script: new or extended chapters, and the 20-minute version's run of show;
- the Operation Ledger walkthrough;
- capture steps for each new screen, captured in both brands.

**Decks** (new revisions saved beside the originals; originals kept):
- **Prison Intelligence (v1, v2, v3):** built by `build_decks.py`; new monitoring slides and the
  captured screens.
- **Pitch** (latest: Draft2), **Product Overview** (latest: Draft1c), **AML Opportunity** (Draft1)
  and **Administration Architecture** (Draft2): hand-made files, edited directly. Each gets:
  - monitoring and alerting as a core capability, with a slide of its own;
  - the one-line description from ADR-115 Amendment 4.

The marketing site's copy is the owner's call: it already names the theme but not monitoring.

## Stage 6 — rehearse (owner approval 3)

Run every demo on a freshly reset deployment, in both brands, from start to finish, before it is
presented. Check that the guides' steps match what is on screen.

## Order and size

The reporting features are a build phase of their own; stage 4 is most of the work. Without the
reporting ADR, only P1, P2, A1 and A2 can be shown. Recommended order:

1. Finish the current deck work.
2. The reporting ADR (stage 3.1).
3. The use-case choice and the demo amendments.
4. The build.
5. Guides, decks and rehearsal.
