# OspreyFlow — User Guide

For analysts: the people who investigate in OspreyFlow. It covers signing in, cases, the graph, the
map, the timeline and the reports, alerts and watches, and how OspreyFlow decides what you can see.
It describes what is built, and says plainly where something is not yet.

The other guides in this folder are the [administration guide](administration-guide.md), for
whoever installs and runs OspreyFlow, and the [developer guide](developer-guide.md), for data
engineers. The screenshots show the synthetic demonstration cases; no real data appears in them.

---

## 1. What OspreyFlow is

OspreyFlow holds a case's people, organisations, accounts, phones, places, documents and events as
one graph, and gives you one workspace — the **Glass** — in which the network, the map, the
timeline and the reports are views of the same working set. Selecting something on the graph selects
it on the map; dimming a period on the timeline dims it everywhere.

Three things about the data run through everything below:

- **What you see is decided for you, and nothing hidden is hinted at.** Every record carries a
  classification and handling codes; you see what your clearance allows, in the cases you have been
  given. A record you cannot see is not drawn, not counted in a figure, and cannot be found by its
  links. The status bar says how many items were hidden by handling — never which.
- **A model's findings are suggestions.** Anything a model produces is *inferred*, drawn dashed, until
  a person confirms it. Nothing is promoted automatically.
- **Records are never merged.** Records that seem to be one person or organisation are linked with a
  score, and shown as one at the strictness the case is set to. Change the strictness and they come
  apart again; nothing was overwritten.

## 2. Signing in

![The welcome page: sign in from here](images/user/01-welcome.png)

Open your deployment's address. The welcome page never asks for your password: **Sign in** takes you
to the deployment's own sign-in page, at `id.` in front of the same address.

![The sign-in page](images/user/02-sign-in.png)

Your administrator invites you. With email set up, you get a link to choose a password; otherwise
they give you a **one-time code** in person, and you choose your password the first time you sign
in. If you forget it, ask your administrator to reset your sign-in. Where your organisation's own
sign-in is set up, the welcome page offers it too.

**Signing out**: the account button at the top right (your name and clearance) has **Sign out**.

## 3. Start

![Start: the places your roles open, what needs your attention, and your recent cases](images/user/03-start.png)

After signing in you arrive at **Start**. It shows the places your roles open — for an analyst, the
**Glass** — with what needs your attention (open alerts, alerts you have claimed) and your recent
cases with your level on each. **G** opens the Glass from here. The OspreyFlow mark at the top left
always brings you back.

## 4. Cases

Everything happens inside a **case**. Your level on a case decides what you may do there:

| Level | You may |
| --- | --- |
| **Viewer** | Open it, browse and query |
| **Editor** | Also change it: add data, expand, edit links, triage alerts |
| **Author** | Also decide who may open it, and which data it reads |

Whoever creates a case is its first Author. **A level never widens what you can see**: a record above
your clearance stays hidden in a case you author. A case you have no level on does not appear at all.

The case menu at the top left switches case and opens the Cases drawer, where an Author manages
**Who can open this case**. A link to a case opens it directly. A case reads only its own
**datasets**: search, paths, Explore and watches all stay within them.

## 5. The Glass

![A case with nothing drawn yet: Where to start](images/user/04-case-where-to-start.png)

| Part | What it is |
| --- | --- |
| **Top bar** | The case menu, search, the view switch (Graph, Map, Reports), Export, and your account |
| **Left rail** | The places: Explore, Alerts, Ownership, Watches, Questions, History, Dashboards, Help — those your rights allow |
| **Canvas** | The graph, the map or the reports |
| **Right column** | The Inspector, Metrics, the query builder and Find connections, stacked; **Full width** and **Hide** |
| **Timeline** | Folded at the bottom until opened |
| **Status bar** | How many nodes and links are drawn, how many dimmed by a filter, and how many hidden by handling |

### 5.1 Where to start

While the canvas is empty — or any time from the rail's **Explore** — **Where to start** shows what
the case holds: counts of each type, the most connected entities, the busiest links and days, groups
and the entities that bridge them, what is new since the last loads, and starter questions. **Add…**
on any entity draws it alone, with its 25 or 50 busiest links, or with all of them.

### 5.2 The graph

![The graph, with its groups shown](images/user/05-canvas.png)

**Selecting.** Click a node; Shift-, Ctrl- or Cmd-click adds or removes one; or draw a lasso. The
selection bar then offers **Expand**, **Show links among these**, **Branch to a new case**,
**Remove from view** and **Clear** (Esc).

**Expanding.** Double-click, or press Enter, to draw a node's links. Right-click (or `\`) opens its
menu: **Show links** lists each kind of relationship with how many there are, so you can draw just
one; **Actions** holds Link to…, Split from…, Find paths to…, Explain cluster, View messages, Branch
selected to a new tab, Set picture, and Mark for suppression. An expansion that would add more than
**500** nodes asks first, offering one relationship at a time, all of them, or nothing. An expansion
past the working set's own limit is refused; reduce what is drawn, or branch, and try again.

**Reading a link.** A link's stroke says where it came from: **solid** from a record, **dashed**
inferred by a model, **dotted** unresolved. Hovering names its type and how many such links join the
two. Right-click a link (or `L`, then `\`) for its menu: its emails, events or messages; **Change
link…**; its change history; a note; or hide it.

**Same-as links.** Records OspreyFlow thinks are one are joined by a same-as link. Its menu offers
**Collapse into one node** (for this view only), **Confirm as the same**, **Mark as not the same**
and **Explain this link**. Confirming or marking needs a reason, kept in the audit with your name.
**Match strictness** at the top of the graph sets how sure a match must be to show records as one —
Strict, Balanced (the default) or Broad — and says how many merged and split.

**Groups.** **Communities** boxes groups of closely linked entities; fold a group from its box, or
press `G` on a node in it. **Layout** offers Organic, Force-directed tree, and Clustered bubbles;
**Arrange** lays everything out afresh. Drag nodes to move them; their positions belong to your view.

**Branching** copies the selection, and the links between it, into a new case of which you are
Author; the case you were in is unchanged.

### 5.3 The map

![The map, with sites, boundaries and hotspot cells](images/user/06-map.png)

The map shows the same working set and selection as the graph. **Add site** places a building's plan
on the map from four matched points and draws a grid whose cells become locations. **Draw boundary**
filters to what falls inside it. **Hotspot cells** counts what is in each cell, and filters as you
choose. If the deployment's basemap is not built, the map says so.

### 5.4 The timeline

![The timeline: daily events across the case](images/user/14-timeline.png)

Open the timeline at the bottom. **Drag across the bars** to choose a period: everything outside it
is **dimmed, never removed**, on the graph and the map alike. The slider under the axis zooms the
axis without filtering. **Play** reveals the network as its events happen, at ½× to 8×. The **⋯**
menu sets exact dates, or overlays another case.

![Cyclical: weekday against hour of day](images/user/15-timeline-weekly.png)

**Cyclical** shows the same events as a grid of weekday against hour, for habits and routines.

### 5.5 Search

![Search: suggestions after two characters](images/user/16-search.png)

Press `/` anywhere (outside a text box) to search. Suggestions start at two characters, across names,
identifiers and titles; choosing one draws it with what is near it, counting first and asking if it
is a lot. **Filters** narrow by entity type, how the text matches, and whether to look only at what
is already drawn.

### 5.6 The Inspector

![The Inspector on a person: properties, relationships, shared contacts, risk and provenance](images/user/17-inspector.png)

Select one node and the Inspector shows its **properties**, its **picture**, its **relationships**
(how many of each, drawn or not — **Expand** draws the rest), the entities it **shares contacts**
with, its **neighbourhood risk** (alerts within two links over the last 90 days, scored on request
and never stored), its **provenance** — from a record, inferred, or unresolved, and when it was first
seen — and the **judgements** that cite it. With several selected it summarises them and the links
between them; with a link selected it shows the link's details, notes, events and history, and lets
an Editor **change the link** (with a reason, and what stands behind it).

### 5.7 Metrics

![Metrics: a ranking by betweenness](images/user/20-metrics.png)

**Metrics** ranks what is drawn by degree, weighted degree, betweenness, eigenvector, PageRank,
clustering coefficient or the clique metric, and can compare two. Choose a row to go to it. Its
filters — relationship strength, a metric's value — dim, never remove. A metric is shown as size,
never as colour.

### 5.8 Find connections

![Find connections: two people, and the routes between them](images/user/18-find-connections.png)

Choose a **From** and a **To** — by search, or the node you have selected — and **Find connections**
says how many degrees apart they are and lists the routes at that distance, then widens one degree
at a time, up to eight. Any route can be drawn on the canvas, marking each node with its distance
from From. **Find paths to…** in a node's menu gives the shortest paths between two selected nodes.

### 5.9 History

![History: each named step, with Restore](images/user/11-history.png)

**History** lists what you did to the view as named steps — "Expanded 36 nodes from 1 seed", "Opened
an alert" — with how much each drew. **Restore** goes back to any of them. "Last change" on the
canvas toolbar opens it too.

## 6. Questions to the model

![Questions: ask about the documents in this case](images/user/12-questions.png)

**Questions** asks the deployment's model about the documents in this case that you can see, and it
answers from them only, citing each — **Draws on** opens the document. What it proposes, you
**Accept** or **Reject**; an accepted proposal enters the graph as *inferred*. A question about more
text than the model takes is refused, saying how much, and kept. **Ask the model about these…** on a
selection of documents starts a case of its own for them.

## 7. Alerts and watches

### 7.1 Alerts

![Alerts: the queue, with an alert's detail and its close box](images/user/09-alerts.png)

The rail's **Alerts** (its badge counts what is open or claimed) holds the alerts the case's rules
raised — structuring, rapid movement, circular flow, screening matches, shared contact details,
unverified customers, and patterns drawn by analysts. **An alert concerning anything you cannot see
is neither shown nor counted.**

Open one to see why it was raised and what it concerns; **Show on the canvas** draws them. **Claim**
it to work on it (**Release** gives it back). **Close as true positive** confirms the node it raised;
**Close as false positive** leaves it a suggestion. Closing needs a reason. Triage needs Editor; a
Viewer reads. The **Rules** tab shows the rules judging this case; an Author deploys and retires them.

### 7.2 Watches

![Watches: hotlists, monitors, and the alerts they raise](images/user/13-watches.png)

**Watches** keeps a **hotlist** of identifiers — a phone number, an email address — each with a review
date: any data that touches one raises an alert. A **monitor** runs a saved pattern against new data.
Both watch only their case's data. **Jump into investigation** starts a case from an alert. An alert
whose evidence you cannot see says only that a match fired.

## 8. Ownership and due diligence

![Ownership: who stands behind an organisation, and its due diligence](images/user/10-ownership-due-diligence.png)

The rail's **Ownership** traces who stands behind an organisation or account: every beneficial owner
at or above the threshold (25% by default), their cumulative share through each chain, and anyone
holding control whatever their share. A circle of cross-holdings is traced once, and said so. **Due
diligence** gives the verification status, risk band and score with each factor's weight, and the
verifying documents. All of it is worked out as you read, from what you can see, and stored nowhere.
**Show the structure on the canvas** needs Editor.

## 9. Reports and dashboards

![Reports → Figures](images/user/07-reports-figures.png)

The view switch's **Reports** shows the case's figures over 4, 12, 26 or 52 weeks: alerts raised each
week, open alerts by age, outcomes, customers by status, held rows. Every figure is **counted for
you**: anything you cannot see is in no figure. A period too long to count says to choose a shorter
one; it never shows part of a chart. Other tabs, as your rights allow: **Trends**, **Packs** (report
packs, exported to PDF), **Published**, **Data feeds** and **Dashboards**.

![Reports → Dashboards: a board drawn inside the Glass](images/user/08-reports-dashboard.png)

**Dashboards** draws the deployment's boards inside the Glass, showing only those you may open. The
same boards are at `bi.` in front of the deployment's address, signed in the same way.

## 10. Judgements

The Inspector's **Judgements** records what you conclude: a statement, how likely it is on the
probability yardstick, and the evidence for and against. A judgement cannot be saved without at least
one supporting reference. Gaps (open, tasked, answered, closed) and assumptions (with what follows if
one is false) are recorded the same way. A judgement is hidden from anyone who cannot read all of its
supporting evidence, and flagged for review when something it cites is corrected or split.

## 11. Export

![Export: the subgraph on the canvas](images/user/19-export.png)

**Export** (on the Graph view) saves what is on the canvas:

| Artefact | File |
| --- | --- |
| **Subgraph** | JSON |
| **Chart** | PNG |
| **Report** | A self-contained HTML page |

Each export is marked — the handling level and the time — and says how many items it left out for
handling. Items that cannot leave are named, with the reason. An item marked *consult originator*
needs a justification and the originator's reference before **Export** is enabled. Every export is
recorded. Report packs export to PDF from the Packs and Published tabs.

## 12. Keys

| Where | Key | Does |
| --- | --- | --- |
| Start | `G` | Open the Glass |
| Anywhere | `/` | Search |
| Anywhere | `?` | The welcome panel, with keys worth knowing |
| Canvas | Tab, Shift+Tab | Move into and out of the canvas |
| Canvas | Arrows | Step to the next or previous neighbour |
| Canvas | Ctrl/Cmd+Arrows | Step within the selection; with Shift, through every node |
| Canvas | Space | Add or remove the focused node from the selection |
| Canvas | Enter | Expand the focused node, or read a document |
| Canvas | `\` | The focused node's or the selected link's menu |
| Canvas | `L`, Shift+`L` | The next or previous link of the focused node |
| Canvas | `G` | Fold or unfold the focused node's group |
| Canvas | `F` | Fit the graph to the view |
| Canvas | Shift+Arrows | Move the selection; with Alt, further |
| Canvas | Delete | Hide the selected link, or remove the selection from view |
| Anywhere | Esc | Clear the selection; close a menu, drawer or reader |
| Forms | Ctrl/Cmd+Enter | Confirm a reason, save a change or a note, ask a question |
| Side panels | Alt+Up, Alt+Down | Move a panel up or down the column |

Every action in the Glass can be reached from the keyboard. Panning, zooming and the lasso are by
pointer only, by design: the arrows, Space and `F` do the same work from the keyboard.
