# OspreyFlow — User Guide

OspreyFlow is an open-source intelligence mapping platform for crime analysis, anti-money-laundering,
fraud detection, and event monitoring and alerting.

For analysts: the people who investigate in OspreyFlow. It covers signing in, cases, the graph, the
map, the timeline and the reports, monitoring and alerts, and how OspreyFlow decides what you can see.
It describes what is built, and says plainly where something is not yet.

The other guides in this folder are the [administration guide](administration-guide.md), for
whoever installs and runs OspreyFlow, and the [developer guide](developer-guide.md), for data
engineers. The screenshots show the synthetic demonstration cases; no real data appears in them.

<!-- document-control:begin -->
## Document control

**Version 1.26** · 2026-11-04 · For OspreyFlow v0.4.5 · Issued

| Version | Date | What changed |
| --- | --- | --- |
| 1.26 | 2026-11-04 | Describes v0.4.5. No change to its content. |
| 1.25 | 2026-11-03 | Rehearsal fixes (build order step 18c). §5.2: **Show links among these** within a number of degrees says when the routes are already drawn; a node put back on the canvas brings back its links. §5.5: a search result chosen goes into the case before it is drawn, so a large draw you cancel leaves the node in the case. §5.4: **Cyclical** makes the timeline tall enough to read the grid; the grid draws correctly with cells chosen or the map open. §5.5: *Add many from a list* says how many different records were found ("37 found, naming 36 different records") and how many records are in the view after adding. §5.8: each route names its links, so two routes through the same people read apart. §5.6: a source file is named by its file name. A large expansion names relationships by their labels. §5.12: the strength legend is read again when you come back to the window. §9: the Figures' **Outcomes** has a column for every closing reason (True match, False positive, Duplicate, No further action, Referred) and one for closed with no outcome; an alert closed as Referred is no longer counted open. Ask the case names the person who asked at once. |
| 1.24 | 2026-11-03 | §2: staying signed in — a window renews its sign-in by itself, and when your session has ended it asks you to sign in again where you are, without losing the page. |
| 1.23 | 2026-11-03 | Rehearsal fixes (build order step 15). §5.12: the Matrix's Strength and Rarity fill in as each answer arrives, read *Working out…* meanwhile, and a refused rarity no longer blanks the strengths. §7.3: *Give to* offers people only, never a service account. §9.1: a pack says some items are *not shown* (you may not see something they rest on, or it has since been taken back, as a reverted load takes back its alerts), no longer "withheld from you"; a close reason that ends with a full stop is not given a second. |
| 1.22 | 2026-11-02 | Checked against the Glass end to end (build order step 10). §7.1: Monitoring's tabs include **Lists** and **Connection strength**, and say which levels see Held rows and Audit. §5.12: the legend marks the composition, not the rarity measure, as a case override (a case cannot choose the measure). §7.6: the *For* choices as the builder words them (*just me*). |
| 1.21 | 2026-11-02 | §5.12: shared-attribute rarity is now worked out by the client's own measure (one less a shared value's share of the pairs linked through values of its kind), with the earlier measure still to choose; the two compositions, standard and client parity, and the raw sum on the client's scale; an influencer triggered by a dataset; a case switched to client parity by its Author. §7.6: a strength figure on the client's scale. |
| 1.20 | 2026-11-02 | New §5.12, How connection strength is worked out: a link's strength from its own count and recency, the influencers that change it (direct links, and a boost from a record that evidences the link, such as an assault), shared-attribute rarity, the legend, the two new filters in Metrics, the Matrix's two sorts, the Inspector's explanation, who changes influencers, and why two analysts can see different rarity. §7.6: a rule on connection strength or rarity. |
| 1.19 | 2026-11-02 | §4: the demonstration cases each starter brings, and their domains; a public dataset's case. |
| 1.18 | 2026-11-01 | §7.5: a hotlist can hold an account number, matched on the account however its spaces are written. §7.4: a money-flow rule judges only movements between accounts its author may see. §7.10: the UK Sanctions List (FCDO) among the lists; the closed OFSI list says so. |
| 1.17 | 2026-11-01 | §7.3: closing an alert takes one of five closing reasons (True match, False positive, Duplicate, No further action, Referred) and words. §7.5 and the left rail: watches, and the alert inbox, are in Monitoring's Watches tab; the rail has no Watches entry. §7.10: UN and OpenSanctions are marked "licence not confirmed", and whoever manages lists sees only their own unit's counts. Ask to search answers on the engine you choose when the case's data may leave (the engine choice). The mark on the top bar is read aloud as "Osprey, go to Home". |
| 1.16 | 2026-11-01 | §7.11: a rule that runs on a schedule, every day or every week, and its runs. §7.12: a second person's approval — for a rule for the whole deployment, and for closing a high-severity alert; a rule's versions. §7.3 and §7.10 point to them, and a list may be refreshed on a schedule. |
| 1.15 | 2026-11-01 | §7.9: the four new AML templates (a high-risk jurisdiction, large cash, a dormant account reactivated, a sudden rise in velocity). §7.10: screening lists — the Lists tab, re-screening when a list changes, and a match confirmed by a person. |
| 1.14 | 2026-11-01 | §7.6–7.8: a rule written as a sentence, blank by blank from the ontology, and its drawn pattern; frequency and amount conditions; Preview on the last 90 days. |
| 1.13 | 2026-11-01 | §9.1–9.3: an alert in a report pack (open or closed, inferred or confirmed); alert trends in the Trends tab; the monitoring figures dashboards receive. |
| 1.12 | 2026-11-01 | §7 rewritten as Monitoring and alerts: the Monitoring place and its one queue for every kind of alert; severity, who may see an alert, giving it to a member, and closing it with a reason; the typologies as rule templates; whom a hotlist's alerts reach. §12: the canvas says the node the keyboard is on. |
| 1.11 | 2026-11-01 | §5.11: the Matrix, the graph as two tables a screen reader can walk, with its keys in §12. |
| 1.10 | 2026-11-01 | §6: an engine marked "under contract" or "no contract", and one the case's data may not reach shown not available, with the reason. |
| 1.9 | 2026-11-01 | §6: choosing the model engine in Ask the case and Ask to search, and what an answer's "Answered by" line means. |
| 1.8 | 2026-11-01 | The opening says what OspreyFlow is for: intelligence mapping, for crime analysis, anti-money-laundering, fraud detection, and event monitoring and alerting. |
| 1.7 | 2026-10-29 | Describes v0.4.1: the top bar wraps to a second line when its items do not fit, and the map keeps what it showed when the timeline opens. |
| 1.6 | 2026-10-28 | A source row is counted from 1 everywhere it is shown: the first row after the header is row 1. |
| 1.5 | 2026-10-27 | Add many from a list; Select what is lit and the weekday-by-hour cell brush on the timeline; the case brief; icons by value; a property condition on a pattern node; graph facts in an answer; Ask to search; a hotlist alert that explains itself; and sources withheld where a case does not read their data. |
| 1.4 | 2026-10-18 | §5.3: accounts where they are held, and payments as lines, on the map. |
| 1.3 | 2026-10-18 | §5.2: link types in the legend, left out of the view or brought back, and the custody links of a prison case. |
| 1.2 | 2026-10-15 | A cover page, contents, a list of figures, and this version history. |
| 1.1 | 2026-10-14 | Cases and their branches shown as one tree; a branch renamed or deleted where it is listed. |
| 1.0 | 2026-10-14 | First issue, with screenshots of the synthetic demonstration cases. |

<!-- document-control:end -->

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
  links. The status bar says how many items were hidden by handling — never which. The same holds
  for where a record came from: a record's sources are named only when every dataset the record
  belongs to is one this case reads (section 5.6).
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

**Staying signed in**: a window renews its sign-in by itself while it is open, so you can leave it and
come back to it as you left it. When your session has ended (you have been away for a long time, or
your administrator has ended it), the window says **Your session has ended** over the page and offers
**Sign in again**, which signs you in in a small window of its own: the page behind it, with the tab,
the selection, the map and anything you have typed, stays as it is. If the sign-in service cannot be
reached, it says so and offers **Try again**.

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

The case menu at the top left lists your cases as a tree: each case with its **branches** beneath
it (a branch is a case of its own, made from nodes you chose — section 5.2), named for how many nodes it
was made from and when, until you rename it. On a branch, the menu's button reads *case › ⑂ branch*.
Each branch's **⋯** offers **Open**, **Rename** and **Delete**; Delete asks once, and the branch leaves
every list for everyone while the case it came from is untouched. Deleting the branch you are in takes
you back to its case. Renaming and deleting are for the branch's Author (an administrator may also
delete). The rail's **Cases** drawer shows the same tree, with **Who can open this case**, which the
Author manages. A link to a case opens it directly. A case reads only its own
**datasets**: search, paths, Explore and watches all stay within them. A record can belong to more than
one dataset; you may see it through any one the case reads, but what it says of where it came from
(its sources) is shown only when the case reads all of them (section 5.6).

**The case brief.** The **Cases** drawer also holds the case's **Brief**: what the case is for.

- **Priority information requirement** is one statement of the question that matters most.
- **Information requirements** are up to twenty, each of up to 2,000 characters, each marked **Open** or
  **Answered**. **Mark answered** and **Reopen** are done by a person; nothing else changes a status,
  and a model never does.
- **Attach…** links a requirement to what answers it: a **Trend**, a **Saved pattern**, an **Assessment**
  or a **Canvas view**, up to ten to a requirement. Choosing an attachment's name opens it where it
  lives: a canvas view opens as a case, a trend opens Reports on its Trends tab, and a pattern or
  assessment takes you to its panel. **Detach** removes the link only.
- Anyone who may read the case reads the brief. Only the case's **Author** edits it (**Edit the priority
  requirement**, **Add a requirement**, **Edit**, **Remove**). Ctrl/Cmd+Enter saves a box and Esc
  cancels it.
- An attachment you may not read is left out entirely: no title, no placeholder and no count. Two
  people with different access can therefore see different attachments under the same requirement.
- Editing the priority, a requirement's text or status, adding one or removing one puts a step,
  "Edited the brief", in **History**. That step cannot be restored, since a brief is not a canvas.
  Attaching and detaching are recorded, but do not appear in History.
- A branch does not inherit the brief.

**The demonstration cases a deployment starts with.** Your administrator may have installed
OspreyFlow from a **starter** (a theme and a domain; administration guide §1a). Each starter brings
the demonstration cases of its domain, all synthetic, each set to its domain's packs (so its reports
and choices fit it). Every pack stays available to the cases you create.

| Starter | The demonstration cases it brings | The cases' domain |
| --- | --- | --- |
| `…-crime` | Prison Intelligence Dataset (synthetic demo); HMP fixture (synthetic demo) | NIEM |
| `…-aml` | Operation Ledger (synthetic demo), with its synthetic screening lists | FIBO |
| `…-fraud` | Fixture Corp (synthetic demo); PaySim only if your administrator downloads and adds it | FIBO |
| `…-cyber` | Cyber intrusion (synthetic demo): a STIX 2.1 threat case | STIX |
| `…-blank` | None, and no demonstration accounts | — |

The theme (`ospreyflow-…` or `govuk-…`) changes only the look: under the GOV.UK theme, the header
names the service your administrator chose, the same on every case. A dataset your administrator
added from outside, such as a VAST Challenge dataset, is a case of its own named after the dataset,
"(public dataset)".

## 5. The Glass

![A case with nothing drawn yet: Where to start](images/user/04-case-where-to-start.png)

| Part | What it is |
| --- | --- |
| **Top bar** | The case menu, search, the view switch (Graph, Map, Matrix, Reports), Export, and your account |
| **Left rail** | The places: Explore, Monitoring (its Watches tab holds your watches), Ownership, Questions, History, Dashboards, Help — those your rights allow |
| **Canvas** | The graph, the map, the Matrix or the reports |
| **Right column** | The Inspector, Metrics, the query builder and Find connections, stacked; **Full width** and **Hide** |
| **Timeline** | Folded at the bottom until opened |
| **Status bar** | How many nodes and links are drawn, how many dimmed by a filter, and how many hidden by handling |

### 5.1 Where to start

While the canvas is empty — or any time from the rail's **Explore** — **Where to start** shows what
the case holds: counts of each type, the most connected entities, the busiest links and days, groups
and the entities that bridge them, what is new since the last loads, and starter questions. **Add…**
on any entity draws it alone, with its 25 or 50 busiest links, or with all of them. **Add many from a
list** (section 5.5) is a fold here too.

### 5.2 The graph

![The graph, with its groups shown](images/user/05-canvas.png)

**Selecting.** Click a node; Shift-, Ctrl- or Cmd-click adds or removes one; or draw a lasso. The
selection bar then offers **Expand**, **Show links among these**, **Branch to a new case**,
**Remove from view** and **Clear** (Esc). Past one degree, **Show links among these** draws the routes
between the selected nodes, says which pairs are not connected, and says when the routes are already
drawn. **Remove from view** and **Clear view** take nodes off the canvas; a node you put back brings
its links in the view back with it.

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

**Link types.** A link's colour says its type where the type has one. Under the types, the
**legend** lists the links in view — each type in its colour, with how many — and each has a box:
clear it to leave that type out of the view, tick it to bring it back (in this tab only; nothing is
removed). **Show links** on a node draws one type at a time, so you can, for instance, follow only
who shared a cell with whom. A prison or custody case (the Prison Intelligence Dataset demonstration case is one) carries the links a
prison intelligence analyst works with: **shared a cell with** (with the cell and the dates),
**co-defendant of**, **in conflict with** (with a reason), **visited** (in person or by video), and a
person's **role in** an incident (an assault, a disorder or a find, with what was found), beside the
phones, calls, accounts and payments any case can hold. Two prisoners who call the same outside
number, or are paid from the same account, are joined through that number or account on the graph,
and the number's or account's calls and payments are on the timeline and the map.

**Icons by value.** A type's icon can depend on one of its properties. An **Endpoint** is drawn as a
neutral device; one whose kind is a phone number is drawn as a phone, a PIN account as a keypad, and an
account as an account. In a prison case an **Incident** is drawn as a parcel over a wall for a
throw-over, a clash for an assault, a crowd for a disorder and a magnifier for a find; an incident of
another category keeps the type's icon. Shape and colour stay the type's. The order is: the entity's
own picture, then the icon you chose for the type (the **Icons** control in the canvas toolbar), then
the icon for the value, then the type's icon. A node without the property, or with a value no icon is
given for, is drawn with the type's icon. The **legend** lists **Icons by value** in view, each with its
meaning, such as "Keypad: Endpoint, endpoint kind handle", and how many; the **Inspector** says "Icon
for this value" for the selected node. Both name an icon only where the canvas draws it. As with every
icon, the icon is drawn only when you are zoomed in to the neighbourhood, and past 10,000 nodes nodes
are dots.

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

The map shows the same working set and selection as the graph. A location is drawn at its point,
and so is an account, where it is held; a link between two things on the map is drawn as a line —
a payment from an outside account into a prisoner's private cash, for instance. **Add site** places a building's plan
on the map from four matched points and draws a grid whose cells become locations. **Draw boundary**
filters to what falls inside it. **Hotspot cells** counts what is in each cell, and filters as you
choose. If the deployment's basemap is not built, the map says so.

### 5.4 The timeline

![The timeline: daily events across the case](images/user/14-timeline.png)

Open the timeline at the bottom. **Drag across the bars** to choose a period: everything outside it
is **dimmed, never removed**, on the graph and the map alike. The slider under the axis zooms the
axis without filtering. **Play** reveals the network as its events happen, at ½× to 8×. The **⋯**
menu sets exact dates, or overlays another case. **Clear filter** removes the period.

**Select what is lit.** With a period chosen, **Select what is lit** replaces your selection with
every node that has a link with at least one event in the period, its two ends included. A link is
*lit* when it has such an event; a node is lit when a lit link touches it. **Undated links are never
lit**: a link with no event has no date to fall in the period, and there is no setting to include it.
The selection bar says so ("Lit in 5 Jan – 30 Apr 2026: undated links are not included") and offers
**Undo select what is lit**, which gives back the selection you had; it is offered while the selection
is still exactly the lit nodes. If nothing is lit, the selection is left alone and it says so. Dates
are UTC. To reach it from the keyboard, set the period with **Set exact dates** in the **⋯** menu.

**Branch to a new case**, pressed while the selection is still what was lit and the period unchanged,
branches only the lit links and the nodes they touch, and the new case's timeline starts and ends
inside the period. Its tab is named for the period, such as "5 Jan – 30 Apr 2026, selected". If the
slice is over the canvas's limit, it says how many and that no tab was made; narrow the period or select
fewer nodes. Change the selection and the branch is an ordinary one.

![Cyclical: weekday against hour of day](images/user/15-timeline-weekly.png)

**Cyclical** shows the same events as a grid of weekday against hour, for habits and routines. It
always draws the case's whole range. Hours and days are UTC. Choosing it makes the timeline tall enough
to read the grid's seven rows; a timeline you have made taller stays as it is.

**Choosing cells.** Drag across the grid to choose the cells (a weekday and an hour each) you want; they
stay outlined and the rest of the grid stays visible. For the keyboard, open **⋯** (**More timeline
options**) and **Choose cells (UTC)**: tick the days (Mon to Sun), set **From hour** and **To hour**
(0 to 23), or press **Weekend**. A drag sets the hours too. **Clear** removes the choice, as does **Clear
filter**. Once cells are chosen, the map and its hotspot cells count only the events that fall in them,
the canvas dims what does not, and the status bar counts what is dimmed as for a period. **Select what
is lit** honours them as well: it needs a period chosen on the density view, and lights only links
with an event inside the period and the cells. Choosing cells alone, with no period, does not offer
it.

### 5.5 Search

![Search: suggestions after two characters](images/user/16-search.png)

Press `/` anywhere (outside a text box) to search. Suggestions start at two characters, across names,
identifiers and titles; choosing one puts it in the case and draws it with what is near it (three
links out), counting first and asking if it is a lot. Cancelling a large draw leaves the chosen node in
the case on its own. **Filters** narrow by entity type, how the text matches, and whether to look only at what
is already drawn. A phone number or account reference is read the same way however you type it, so
`07700 900640` finds the number held as `+447700900640`.

**Add many from a list.** The list button beside the search box (**Add many from a list**), and the fold
of that name in **Where to start**, take a list of identifiers and draw what is found. Adding needs
Editor on the case; without it, the box says so.

1. Paste identifiers into the box, or choose a `.txt` or `.csv` file (its first column; a first row that
   is a header such as "identifier" or "prison number" is left out). They may be prison numbers,
   National Insurance numbers, phone numbers or account references, one a line or separated by commas
   or spaces. A number written with spaces, such as `+44 7700 900640`, is one number.
2. Press **Count**. It says, for example, "40 identifiers read. 37 found, naming 36 different records.
   3 matched nothing you can see. 1 repeated." Nothing is on the canvas yet. Changing the text clears the count, so a count is
   always of what you would add.
3. Press **Add** to put the nodes on the canvas without their links; **Show links among all** in the
   canvas toolbar's View group then draws the links. **Add with all links** draws the links among
   the nodes added and those already there instead. For a very large view it adds the nodes without
   looking for links, as Expand does. It then says how many records are in the view ("36 records are
   in the view"): each record once, one already on the canvas included. **Cancel** (or Esc) empties
   the box.

What the figures mean. *Found* counts every identifier that resolved, repeats included. *Matched
nothing you can see* is one figure for an identifier that does not exist and one you may not see: the
words, the counts and the work done are the same either way, so a list cannot be used to test whether a
hidden person exists. *Repeated* counts identifiers that name what an earlier one did, so three
spellings of one number count three times as found, twice as repeated, and as one record; when the
records found are fewer than the identifiers found, the count says how many different records there are. If more records than the lookup reads
share a value, it says so, "could not be told apart", rather than guessing. A number is matched only to a
phone number and an account reference only to an account: a PIN holding the same digits is not a match.

The limit is **5,000** identifiers at once. More is refused, naming the figure, and nothing is added;
split the list. A list that would take the canvas past its limit adds nothing, and says how many it would have been against the limit.
The box is never shown an identifier back, only counts.

### 5.6 The Inspector

![The Inspector on a person: properties, relationships, shared contacts, risk and provenance](images/user/17-inspector.png)

Select one node and the Inspector shows its **properties**, its **picture**, its **relationships**
(how many of each, drawn or not — **Expand** draws the rest), the entities it **shares contacts**
with, its **neighbourhood risk** (alerts within two links over the last 90 days, scored on request
and never stored), its **provenance** — from a record, inferred, or unresolved, and when it was first
seen — its **source**, the file and row it came from (its file name, never the server's folder, and
"row 3"), the **icon for
this value** where the type has one (section 5.2), and the **judgements** that cite it. With several selected it summarises them and the links
between them; with a link selected it shows the link's details, notes, events and history, and lets
an Editor **change the link** (with a reason, and what stands behind it).

**Sources withheld.** A record can belong to more than one dataset, and a case reads only some. Its
sources are named only if the case reads every dataset the record belongs to. When it does not, where
the sources would be listed, the Inspector's **Source**, a link's details and the messages view
(**View messages**) say "Its sources are in data this case does not read". They never say "No sources
recorded": there are some, and they are not this case's to see. The node or link itself is still
shown, as you may see it; only where it came from is held back. The same applies in an alert (section
7.5). If an Author widens the case's datasets, records already on your canvas may keep saying this
until you open the case afresh.

### 5.7 Metrics

![Metrics: a ranking by betweenness](images/user/20-metrics.png)

**Metrics** ranks what is drawn by degree, weighted degree, betweenness, eigenvector, PageRank,
clustering coefficient, the clique metric, connection strength or shared-attribute rarity (§5.12),
and can compare two. Choose a row to go to it. Its filters — relationship strength, a metric's
value — dim, never remove. A metric is shown as size, never as colour.

### 5.8 Find connections

![Find connections: two people, and the routes between them](images/user/18-find-connections.png)

Choose a **From** and a **To** — by search, or the node you have selected — and **Find connections**
says how many degrees apart they are and lists the routes at that distance, then widens one degree
at a time, up to eight. Each route names its people and its links ("Vance, Callum → Fairlop, Dominic →
Skellion, Rory, by passes items to, then associate of"): two routes through the same people by
different links are different routes. Any route can be drawn on the canvas, marking each node with its distance
from From. **Find paths to…** in a node's menu gives the shortest paths between two selected nodes.

### 5.9 History

![History: each named step, with Restore](images/user/11-history.png)

**History** lists what you did to the view as named steps — "Expanded 36 nodes from 1 seed", "Opened
an alert" — with how much each drew. **Restore** goes back to any of them. "Last change" on the
canvas toolbar opens it too. An edit to the case's brief appears as "Edited the brief" and cannot be
restored (section 4).

### 5.10 The query builder

The **query builder**, in the right column, draws a pattern of nodes and links, counts what matches
(**Preview**, "~12 matches") and finds it (**Run**). Under **Add to the pattern** you add a node by type
or pin one you have found, and connect two. Under **Save this pattern** and **Load a saved pattern**
you keep and reuse them.

**A condition on a node.** A node can be narrowed by what one of its properties says. On a node, choose a
property, type a value and press **Add condition**: "people held at an establishment whose `niu_area` is
North Wing" is two nodes, one link and one condition. Each condition is listed, as `niu_area = North
Wing`, with **Remove**.

- It is an equality: the property equals the value you typed. There is no "not", no range ("more than",
  "since"), no list of values and no "contains".
- A node takes up to three conditions, each on a different property; setting a property again replaces
  its value.
- Only text properties the case's data model marks as searchable are offered, and never a sensitive
  one. A pattern that names a sensitive or unsupported property, however it reached the server (a
  saved pattern, a model's proposal, a monitor), is refused with the property named, before anything is
  counted, and is never stored. A number, date or yes-or-no property is refused as not supported.
- The condition counts and runs inside what you may see, like the rest of the pattern: a hidden node
  that would have matched leaves no trace in the count.
- A saved pattern, a monitor and a rule built on it all carry the condition.

**Ask to search.** Above the pattern, **Ask to search** takes a question in words: "who shares a visitor
with the principal?". Press Enter or **Ask**. The model is given only your question and the case's
vocabulary: the entity types, the link types with their ends and direction, and the names of the
searchable text properties. It is not given your data, and it cannot run anything. It proposes a pattern,
which is drawn in the builder with a one-line explanation, a count, and the note "A model proposed this
pattern. Check the pattern before you run it." Nothing runs until you press **Run**, and running changes
nothing in the case. A proposal is a suggestion, not a finding.

- "The principal" or "the selected person" mean what you have selected, and only nodes you may see.
- A proposal is a new, unsaved pattern. **Save** never overwrites the pattern it replaced, and **Restore
  the previous pattern** brings that back. If you edit the pattern while the model is working, the
  proposal is dropped with a message, and you ask again.
- **"Could not express the question as a pattern."** The model's answer used a type, link, property or
  value the case does not have, or something the builder cannot draw. The builder cannot draw
  absence ("who has no phone") or ranges ("since 1 January", "more than five"). Rephrase the question,
  or draw the pattern yourself.
- A small local model will sometimes propose a wrong pattern. That is why the pattern and its count come
  first. It does worst on questions about a particular account, number or handset, since the kind of
  an endpoint is not something a pattern can match. For "more than one" questions, two nodes of one
  type are not forced to be different, so a count can include a node matched twice.
- Asking needs the right to ask the model, and Viewer on the case.

### 5.11 The Matrix

**Matrix** in the view switch shows the same working set as the graph, as two tables: **Entities**
and **Links**. It is the way to work through the graph with a screen reader, or whenever a list reads
better than a picture.

- **Entities** has a row for each node on the graph: its name, as the graph labels it; its type; its
  own marking; its provenance, in words, so a node a model proposed reads **Inferred** until someone
  confirms it; and how many links it has in view. **Links** has a row for each link: its type, the two
  ends, its marking and its provenance.
- The tables hold only what the graph holds. What you are not cleared to see is not in them, and they
  give no count of it. A node a filter dims stays in the table and says **Dimmed by filter**.
- Choose a column's heading to sort by it; choose it again to reverse. Each table's caption says how it
  is sorted and which rows are shown. A long table is shown a hundred rows at a time, with **Previous**
  and **Next**, and the caption says so: "Rows 101 to 200 of 12,481". Nothing is left out without
  saying so.
- The selection is the graph's. Select a row and the Inspector shows that node; go back to **Graph** and
  it is selected there. What you selected on the graph is selected in the Matrix, which opens on the
  page that holds it.
- **Expand** on a row opens the graph and expands that node there, with the same preview and limits as
  expanding it on the graph. **Show** opens the graph with that node selected and centred.
- The Matrix lists the whole working set. Groups folded on the graph, links hidden from the view and
  link types left out from the legend are shown in full.

From the keyboard, each table is one Tab stop. The arrow keys move between cells, Home and End to the
start and end of a row, Page Down and Page Up between pages. Enter selects the row's node; Space adds
it to the selection or takes it out.

### 5.12 How connection strength is worked out

How strong a link is drawn rests on three ideas. Each can be seen, filtered and explained on its own.

**1. The link's own evidence.** A link's stored weight comes from that link alone: how often it
occurred, against what is heavy for its type (forty calls, twelve weeks in one cell, six payments),
and how recently, halving every ninety days. A standing link (custody, family, co-defendants, group
membership) has a fixed weight. No other link moves it, so nothing you cannot see changes it.

**2. Influencers.** An influencer changes how strong a kind of link is drawn when you look at it:

| Part | What it says |
| --- | --- |
| **What triggers it** | A record that evidences the link: for example an Incident whose category is assault, disorder or find, at one end of the link or involving both people. Or **a dataset**: every link in that dataset (an assaults table, say), as the client's own code boosts a whole table. **Direct links** have no trigger. |
| **Which links it changes** | Named link types, such as *In conflict with* or *Role in*; or *a pair linked through a shared value* (two people who share a phone, say), which takes an added boost only. |
| **The change** | **Add** a boost (the usual), **multiply**, set a **floor** (at least this strong), or **exclude** (no stronger than its stored weight). |
| **Its size, and a label** | The label is what the legend shows. |

OspreyFlow ships two. **Direct link**: calls, money transfers, visits and cell shares are drawn
stronger than links that are only inferred or shared. **Evidenced by an assault, disorder or find**:
a role in such an incident, and a conflict, association or cell share between people in one, are drawn
stronger. Their sizes are calibrated so that a boost moves an ordinary link about as far as doubling
its count would, and are marked "to be confirmed with the client". Boosts add up.

**An influencer applies only if you may see the record that evidences the link,** or, for a dataset,
only if your case reads that dataset. An assault report above your clearance never thickens a line
you can see, so it never tells you it exists; a dataset your case does not read is not named in your
legend at all. The stored
weight never changes: influencers are applied as the link is read, so a change takes effect at once.

**3. Shared-attribute rarity.** Two people who share something few others share are more interesting
than two who share what everyone does. A thing two people of one kind share (a cell, a phone number, a
visitor, a report, a group) is a **shared value**. By default rarity is worked out as the client works
it out: a value held by *k* people links *k × (k − 1) / 2* pairs, and its rarity is one less its share
of all the pairs linked through values of its kind. A phone two people share, among phones that link
few pairs, scores near 1; the prison everyone is held in scores near 0. Two people take the rarity of
the rarest value they share. Your installation may choose the earlier measure instead, **inverse
frequency**, which adds, for each thing two people share, the logarithm of how many people there are
over how many share it; the legend says which is in force. It is worked out per dataset unless you
choose across the case's datasets, and **only over what you may see**: if two analysts have different
access, they can see different rarity for the same pair, and both are right for what each may see.
Rarity is its own measure, never folded into the strength, except under client parity (below).

**Two compositions.** How the three ideas make a strength is the installation's choice, shown in the
legend:

| Composition | Strength is | Drawn on |
| --- | --- | --- |
| **Standard** (shipped) | the link's stored weight, from its own count and recency, with the influencers applied | 0 to 1 |
| **Client parity** | rarity plus the influencers' added boosts, with no count and no recency: the client's own sum | 0 to 1, through a curve that keeps the sums' order; the Inspector also shows the **raw sum on the client's scale** |

Under client parity, a stored link's rarity is that of the link itself among the links of its type you
can see in its dataset (one less one over how many there are), and a pair linked through a shared
value takes that value's rarity. Only added boosts count in the sum: a multiplier, floor or exclusion
is left out, and the legend says so. Because rarity is worked out over what you may see, so is a
client-parity strength. An installation chooses its composition in the same way as its influencers (a
proposal and a second person's approval); a case's Author may switch one case to client parity, to
compare the two on the same case, and back.

**Where you see it:**
- **The legend** lists, under *Connection strength*: the composition in force (marked **Case
  override** if the case chose it); the rarity measure, which only the installation chooses; every
  influencer in force in the case — what triggers it, the links it changes, the change and its size,
  and where it came from (shipped, installation-wide, or **Case override**); which link types count
  as direct; and the rarity note. It is read again whenever you come back to the window, so a change
  the case's Author made elsewhere shows when you return.
- **Metrics** (§5.7) offers *Connection strength* and *Shared-attribute rarity* to rank by and to
  filter by. Choose one under **Filter** and slide **Metric value at least**: a link below the
  strength, and a person none of whose links reach it, fade; with rarity, a person whose rarest
  pairing in view is below it fades. Nothing is removed.
- **The Matrix** (§5.11) gives each link its **Strength** and the **Rarity** of its two ends, and sorts
  by either. Each column fills in as soon as its answer arrives (the strengths in a second or two, the
  rarity of a large view's every pair can take longer) and reads **Working out…** until then. A link
  with no strength you can see reads **Not worked out**; two ends with nothing rare to share (of
  different kinds, or in no common dataset) read **None**. If the rarity is refused (a view with too
  many pairs) the strengths still show, and the line above the table says why.
- **The Inspector** explains a selected link under **Connection strength**: its count against what is
  heavy for its type, when it was last seen, the rule and weights version it was worked out under,
  each influencer that changed it and the kind of record (or the dataset) that evidenced it, and what
  its two ends share, rarest first, with the measure named. Under client parity it shows instead the
  link's rarity term, each boost added, and the **raw sum on the client's scale**, beside the strength
  it is drawn at. With two people selected, **What these two share** does the same for them.

**Who changes influencers.** An installation-wide set is proposed in **Monitoring → Connection
strength** by someone holding the right to manage influencers, and takes effect only when **another**
person with that right approves it; the proposer can withdraw it but never approve it, and every
version is kept; a version may also choose the composition and the rarity measure. A case's **Author**
may add influencers for that case, switch off installation-wide ones in it, or choose its composition
under *How strength is worked out in this case*; that needs no second person, because it changes only
that case, and the legend marks it. Both are recorded in the audit.

**Rules on strength.** A rule written as a sentence (§7.6) may say "and the connection strength
between it and … reaches X", or "… the shared-attribute rarity between it and another … reaches X". A
strength figure is on the drawn scale (0 to 1) or **on the client's scale** (the raw sum, which only
client parity has: under the standard composition such a rule raises nothing). It is previewed like
any other, and judged as its author, on what its author may see: it never raises an alert on evidence
its author could not read.

## 6. Questions to the model

![Questions: ask about the documents in this case](images/user/12-questions.png)

**Questions** asks the deployment's model about the documents in this case that you can see, and about
**graph facts**. It answers from those only, citing each — **Draws on** opens a document. What it
proposes, you **Accept** or **Reject**; an accepted proposal enters the graph as *inferred*.
**Ask the model about these…** on a selection of documents starts a case of its own for them. Asking
needs Editor, and at least one document you can see in the case.

**Graph facts.** Along with the documents, the model is given a numbered, plain account of the graph
around what you have selected and one link beyond it (the whole view when nothing is selected). A
timeline period, if one is set, limits the links and events to it. The account lists each entity by type
and name; each link among them as a fact, `[G-1]`, `[G-2]`, with its type, its two ends by name, its first
and last date, how often it occurred, its dataset's label and whether it is direct or inferred; and the
events for each month. It holds only what you may see, and never an identifier of the system. It has no
path facts: a question about a connection is answered from the links it holds.

In an answer, each `[G-n]` is a button, "Select [G-1] on the canvas". It selects what the fact stands
for and brings it into view: the link if one drawn link is meant, otherwise its nodes. A fact the model
cites that was not in the account it was given is dropped and counted among the items left out.

The documents and the graph facts share one limit. Over it, the question is refused, saying how many
characters each came to and the limit, and that nothing was sent: narrow the selection, narrow the timeline
window, or branch the case, then ask again. Your question stays in the box. Nothing is trimmed. An
answer is shown later only to someone who could see every item it was built from, so a reader cleared
lower does not see an answer built on events above their clearance. An answer kept before that was
recorded may still be shown as before.

**Choosing the engine.** Where the deployment offers more than one model engine, a **Model engine**
choice sits above your question: the deployment's own model, and any provider your administrator has
enabled, such as Gemini. The one your administrator chose is selected; change it before you ask to use
another. Where only the deployment's own model is offered,
there is no choice to make, and none is shown. Choosing an engine is a request, not a promise: material
your deployment may not send outside is always answered by its own model, whatever you choose. If an
engine cannot be used — it is no longer enabled, or has no key — the question is refused in words and
nothing is sent; choose another and ask again.

**Engines you cannot choose, and why.** Beside each provider the choice says **under contract** or
**no contract**: whether your organisation holds a privacy agreement with that provider. Your
administrator also decides, for each dataset, whether its material may be sent to a provider at all:
never, only to one under contract, or to any. An engine your case's data may not reach is still listed,
marked **not available**, and cannot be chosen; the reason is written beneath the choice, for example
"Gemini: Not available for this case: “Enron corpus” is set to egress none, never sent to a hosted
engine such as Gemini." If the engine your administrator made the default is one of these, the
deployment's own model is chosen instead. Every dataset starts at "never", so until your administrator
changes yours, every question is answered by the deployment's own model.

**"Answered by …".** Under each answer, a small line says which engine and model produced it, for
example "Answered by Gemini (gemini/gemini-2.5-flash)" or "Answered by This deployment's own model
(qwen2.5:7b-instruct)". It is what the deployment says it used, not what you chose. An answer kept
before engines were named has no such line. **Ask to search** shows the same choice and line, and the
choice applies there too: your question is about the case, so it goes under the case's handling and
from the case's datasets, through the same two checks as Ask the case. It reaches the engine you chose
only when the case's material, as you see it, may leave the deployment and every dataset of the case
allows that engine; otherwise the deployment's own model answers, and its line says so.

To ask in words for a pattern rather than an answer, use **Ask to search** in the query builder (section
5.10).

## 7. Monitoring and alerts

### 7.1 The Monitoring place

![Monitoring: the one queue, with a hotlist alert open](images/user/09-monitoring.png)

The rail's **Monitoring** (its badge counts what is open or claimed) is the one place for alerts. Its
tabs are **Queue**, **Rules**, **Watches**, **Lists** and **Connection strength**, and, by your level in the
case, **Held rows** (an Editor or Author) and **Audit** (an Author or an administrator).

**The queue holds every kind of alert you may see**, in one list:

- **rule alerts**, raised by the case's rules — structuring, rapid movement, circular flow, screening
  matches, shared contact details, unverified customers, and patterns drawn by analysts;
- **hotlist alerts**, when data touches an identifier on a hotlist (section 7.5);
- **watched-pattern alerts**, when a monitor's saved pattern matches new data.

**An alert concerning anything you cannot see is neither shown nor counted**, whatever its kind.

Each row says its **severity**, what kind it is and what it found, then where it stands (open, or
claimed and by whom), **who may see it**, how long it has waited ("2 hours old") and when it was raised.
The most severe come first, then the newest. **Show**, **Kind** and **Severity** above the list choose
which alerts to list; the choice is made by the server, so a count always means what it says.

### 7.2 Severity and who sees an alert

Every alert is **high**, **medium** or **low**. Until rules can set their own (a later release), each
kind has its own:

| Alert | Severity |
| --- | --- |
| A hotlist match | High |
| A screening match | High |
| Shared contact details | Low |
| Any other rule, and a watched pattern | Medium |

Who may see an alert is shown on its row:

- **The case team**: a rule alert reaches every member of the case.
- **Shared with team …**: a watched pattern's alert, and a hotlist's alert when its owner has shared
  it, reach the owner and the people of the owner's **unit** (the unit your administrator gave your
  account).
- **Only its owner**: a hotlist kept to its owner, and an alert raised before teams existed.

### 7.3 Working an alert, and closing it

Open one to see why it was raised and what it concerns; **Show on the canvas** draws them. **Claim** it
to work on it (**Release** gives it back). A rule alert can also be **given to** a member of the case:
choose them by name under **Give to**, then **Give**. *Give to* lists the case's Editors and Authors who
are people; an account a service or a loading script uses is never offered. An alert shared with a team, or its owner's alone,
is claimed by someone who can see it, never given to another person.

**Closing needs a reason, in two parts.** Choose one **closing reason** — **True match**, **False
positive**, **Duplicate**, **No further action** or **Referred** (the arrow keys move between them) —
and say why in words; **Close the alert** stays unavailable until you have done both, and words of only
spaces are refused. **True match** confirms the node it raised; every other reason leaves it a
suggestion. OspreyFlow accepts no reason outside this list. Triage needs Editor; a Viewer reads. **Closing a high-severity
alert needs a second person** (§7.12): closing it proposes the close, and another member approves it.

### 7.4 Rules and templates

The **Rules** tab shows the rules judging this case; an Author deploys and retires them. Above the
form, **Templates** lists the typologies as named starting points (the four new AML templates are in
§7.9), grouped by the work they
serve (anti-money-laundering transaction monitoring, KYC, any case), each with what it looks for and
the severity of its alerts. **Use** fills the form with the template's defaults and puts you on the
rule's name; change anything, then **Deploy**. Everyone in the case sees the templates; only an Author
has **Use**. A rule can also be written as a sentence (§7.6).

The money-flow templates (structuring, rapid movement, circular flow) judge each load's movements with
the movements around them, and only those whose two accounts the rule's author may see, in the rule's
own dataset: a movement between accounts hidden from them shapes no finding.

### 7.5 Watches, and whom a hotlist's alerts reach

![Watches: hotlists, monitors, and the alerts they raise](images/user/13-watches.png)

The Monitoring place's **Watches** tab keeps a **hotlist** of identifiers — a phone number, an email address, an account
number — each with a review date: any data that touches one raises an alert. An account number is
matched however its spaces are written: `GB58 LOYD 3096 1700 7099 43` and `GB58LOYD30961700709943` are
the same account. A **monitor** runs a saved pattern against new data.
Both watch only their case's data. Under them, the **Alert inbox** lists what your hotlists and
monitors raised; **Jump into investigation** starts a case from an alert. There is no separate
Watches place on the left rail: open **Monitoring**, then **Watches**.

**Who its alerts reach.** Each hotlist says who its alerts reach in the Monitoring queue: **Only me**,
or **Me and my team**. A new hotlist starts from your deployment's choice (only you, unless your
administrator has chosen otherwise); change it when you make the hotlist, or later on its row. A
hotlist made before this choice existed reaches only you until you change it. Where your deployment
fixes the choice, the panel says so ("Alerts reach only you. The deployment sets this.") and offers
none. A match on data you cannot see is never shared with your team. An alert
whose evidence you cannot see says only that a match fired.

**A hotlist alert explains itself.** In **Watches**, under **Alert inbox**, a hotlist alert is headed
"Hotlist alert" and reads, for example:

- "Hotlist: 07700 900640 · review by 31 Jan 2027": the identifier **as you typed it**, and the
  hotlist's review date. If OspreyFlow could not read the text as a phone number or other known kind,
  it was kept as written, and the line says "(kept as written)".
- "Matched: Endpoint +447700900640": the type and name of what it matched.
- "From: pid_seized_comms_batch2.csv, row 3; pid_pin_calls.csv, 2,013 rows": the files the matched record
  came from, and the row in each, or how many rows. Up to five files are named, in the order they were
  first seen; the rest are counted, "and 3 more files", not cut. Where a source has no row, it counts
  records instead.

**Row numbers count data rows from 1**: the first row after the header is row 1, so "row 3" is the
third data row, the fourth line of the file. The Inspector's source, a link's details, Verify's
rejected rows and held rows count the same way. Where two loads of a file
with the same name matched, each is listed. **Jump into investigation** is as it was. Raw rule and node
identifiers are no longer shown.

Only the hotlist's owner sees the identifier and review date, and an alert on another analyst's hotlist
is not listed to you. An alert about something you can no longer see says only "A match fired — no
evidence visible to you." If the matched record was removed from your view between the two reads, the
alert says "Evidence no longer available." and cannot be jumped into. **Where a matched record belongs
to data this case does not read**, the alert names its type and name and says "its sources are in data
this case does not read", with no file and no row (section 5.6): a file name is as much a source as a
row.

### 7.6 A rule written as a sentence

![A rule written as a sentence, its drawn pattern, and its preview on the last 90 days](images/user/22-rule-sentences.png)

On the **Rules** tab, **Write a rule as a sentence** builds a rule from blanks, read as one sentence:
*When a* subject *whose* conditions, *and is* related to something, *how often*, *then* raise an alert.
Every blank is a choice from a list made from the deployment's ontology — its types, their properties
and its link types — so there is nothing to type that could fail to be understood.

- **Subject.** A type, grouped as people, objects, locations, events and organisations.
- **Whose.** Up to five conditions on the subject's properties: *is*, *is one of*, *is above*, *is
  below*, *is within a time window*, or, for a location, *is within a drawn area* (entered by its four
  corners). A property marked highly sensitive is never offered.
- **And is.** Optionally: *linked by* a link type to something; *within* 1 to 4 *steps of* something
  of a type; *at a location in a drawn area*; *on one of my hotlists*; or, for a person or an
  organisation, *on a screening list* at a name match you choose.
- **How strongly connected.** Optionally: *the connection strength* between the subject and something
  it is linked to (by a link type, or any; to a type, or anything) *reaches* a figure up to 1, or *on
  the client's scale* a raw sum up to 10 (met only under client parity); or *the
  shared-attribute rarity* between it and another of its type *reaches* a figure, per dataset or across
  the case's datasets (§5.12). Both are read from the stored graph, so the rule runs after commit or on
  a schedule, and both are worked out as you, the rule's author, may see them.
- **Then.** The alert's severity; whether it goes to the case team or is labelled for your team; and
  when the rule runs — after each load commits, or before it. Before commit you also choose what a hit
  does: load with its alert, or hold its rows for a reviewer in **Held rows**. A rule that names a link
  runs after commit, since a link is read from the stored graph.
- **For.** *just me* (the alerts reach you alone, like a monitor's), *this case*, or — for an
  administrator — *the whole deployment*, which watches every case's loads.

**Show the drawn pattern** shows the same rule as the Query builder would draw it. Once deployed, the
pattern is saved among your patterns, and you can open and change it there: the rule follows the
pattern as it now reads. **Read a saved pattern as a sentence** goes the other way, from a pattern
you drew to a sentence. A pattern a sentence cannot say (more than one link, or a pinned node) is
refused in words.

Deploying needs a name. A case Editor may deploy a rule *just for me*; a case Author deploys one for
the case; only an administrator, who is also the case's Author, deploys one for the whole deployment.
A sentence that names something the ontology does not declare is refused, naming the blank.

### 7.7 How often: frequency and amount conditions

A sentence may also say how often:

- *a number of times or more within some days* — for example, present at a location 3 or more times
  within 7 days;
- *a total amount over a figure within some days* — the total of a link's declared amount, such as a
  payment's amount, over 10,000 within 30 days;
- *for the first time ever* — the subject's first event of that link type.

The events counted are those of the link type you choose, with the subject at either end. They are
counted as the rule's author: an event you may not see adds nothing to a count or a total, and is
never a "first".

### 7.8 Preview on the last 90 days

**Preview on the last 90 days** runs the rule as you, over the case's stored data, and says how many
alerts it would have raised, with up to five of them. Use it to set a threshold against evidence
before you deploy. A preview raises no alert and writes nothing. It counts only what you may see, so
it says nothing about anything hidden from you. If the rule would judge more subjects than the
working-set limit, the preview is refused and counts nothing: narrow the sentence and preview again.
Frequency conditions are counted over the 90 days.

### 7.9 The AML templates: jurisdiction, cash, dormancy and velocity

![The Rules tab: the AML templates, and the form filled from "High-risk jurisdiction"](images/user/24-aml-templates.png)

Four templates watch a case's money movements (its *transacted* links), each with settings you choose
and no formula to write:

- **High-risk jurisdiction** — a payment to or from an account held in a jurisdiction on your list.
  Type the list as two-letter country codes, separated by commas (for example `XA, XB`): the list is
  part of the rule, so your organisation's policy list is what you enter. An account's jurisdiction is
  its IBAN's country code, the IBAN's first two letters; an account whose number is not an IBAN has no
  jurisdiction here.
- **Large cash** — cash paid in, drawn out, or either, of an amount at or over a threshold (10,000 by
  default) in one movement.
- **Dormant account reactivated** — an account moving money again after a number of days (180 by
  default) without a movement. An account that has never moved before is new, not dormant.
- **Sudden rise in velocity** — an account whose movements over the last days (7) run at a factor (3)
  or more of its own daily rate over the days before (90), with at least a minimum (5) in the last
  days; measured by the number of movements or by the amount moved. An account with nothing in those
  days before has no rate to rise from and raises nothing.

Each raises a medium-severity alert in the queue, in words: the movement, the accounts and what made it
a finding. They judge only movements and accounts you could see as the rule's deployer: a movement
hidden from them neither wakes a dormant account nor adds to a rate. The last two compare an account
with its own stored past, so they run after each load commits.

### 7.10 Screening lists, re-screened when they change

![The Lists tab: each list's version, entries, last update and state, the latest refreshes, and subscribing](images/user/23-screening-lists.png)

The **Lists** tab shows each sanctions, PEP or adverse-media list the deployment screens against: the
list it is (OFAC, the FCDO's UK Sanctions List, the UN or EU consolidated list, OpenSanctions, or HM
Treasury OFSI's, which closed on 28 January 2026 and is marked "Closed list"), its version, how
many entries it holds, when it last changed, its licence, and its state — up to date, not yet read, or
why its last refresh failed, in words. A list read from a file that is not in its publisher's format is
left as it was, and says so.

When a list changes, OspreyFlow re-screens every customer in every case that has a **Screening on
onboarding** rule (§7.4) against **the entries that changed only** — those added and those whose names,
date of birth or country changed. An entry that did not change was screened when it arrived, so it
raises nothing again. Each new match raises a high-severity screening alert in that case's queue,
naming the customer and the list entry, with its score. Like every screening match, it is a suggestion:
the link between the customer and the listed party is inferred until a person confirms it, by closing
the alert as a **True match** (§7.3). Customers are screened as the rule's deployer and within the case's
datasets, so no one is screened, or alerted on, outside what that person may see.

**Licence not confirmed.** The **UN** and **OpenSanctions** lists are marked "Licence not confirmed",
with the reason: no open licence was found for the UN list, whose general terms allow personal,
non-commercial use only; OpenSanctions is CC BY-NC 4.0, and screening in a business is commercial use,
which needs its own data licence. Until a licence is confirmed, these connectors read OspreyFlow's
synthetic lists only.

Administrators and data engineers subscribe to a list and refresh it from this tab (the administration
guide, §9.5, says how), and may have it refreshed every day or every week; the **Schedule** column
says when, or "By hand only". They see how many customers each refresh re-screened, and the alerts it
raised, **in their own unit only**. Everyone else sees the lists, not those numbers.

### 7.11 A rule that runs on a schedule

![A rule written to run every day: its schedule, its runs, and the versions it has had](images/user/25-scheduled-rule.png)

A rule written as a sentence (§7.6) runs as data loads — before or after each load commits — or **on a
schedule**. Choose **Runs: on a schedule**, then **Every** day or week, the day for a weekly rule, and
the hour (UK time). At each run the rule looks at what is already stored over the last day or week,
as you see it, and raises an alert for each new finding, once.

- **It runs as you**, its author, never as the system: it judges only what you may see, and only
  while you may still sign in, deploy rules and are still an Author of the case (an Editor, for a rule
  just for you).
- **Schedule and runs**, under the rule, says when it runs next and what each run did: how many
  alerts it raised, or why it did not run, in words. A run the deployment missed while it was down is
  said too; after downtime only the latest run happens.
- **If it is refused three times in a row** — say, because you can no longer sign in — it stops, and
  says why. Changing the rule starts it again.
- A rule for the whole deployment does not run on a schedule: it is judged within each case as that
  case's data loads.

### 7.12 A second person's approval

![A rule for the whole deployment waiting for a second person, and a high-severity alert whose close waits for approval](images/user/26-second-person.png)

Two decisions need a second person with the right, and the person who proposed one can never approve
it.

**A rule for the whole deployment** (§7.6) — deploying it, changing it or retiring it. A new one is
listed as *not running: waiting for a second person's approval*, with who proposed it; a change or a
retirement waits beside the rule, which runs as it stood until then. Another administrator who is an
Author of the case sees **Approve** and **Reject** (with a reason); a rejected rule never runs. A rule
for one case, or just for you, is not held up: it runs as soon as it is deployed or changed.

**Closing a high-severity alert** that someone else may see. Choosing a closing reason, writing why
and **Propose the close** proposes the close: the alert stays in the queue as *Closing*, with your reason. Another
member who triages alerts in the case opens it and chooses **Approve the close**, or **Send back**
with a reason, which returns it to you, claimed. You may withdraw your own proposal the same way. An
alert only you can see (your own hotlist's, kept to you) has no second reader, and you close it alone.

**Every rule keeps its versions.** **Versions**, under a rule, lists each one: what it did (deployed,
changed or retired), who made it and when, and who approved or rejected it. A changed rule runs as the
person who wrote the change, since it is their judgement now. Everything here is in the case's rule
audit.

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
week, open alerts by age, outcomes (open, claimed, each closing reason, and closed with no outcome),
customers by status, held rows. Every figure is **counted for
you**: anything you cannot see is in no figure. A period too long to count says to choose a shorter
one; it never shows part of a chart. Other tabs, as your rights allow: **Trends**, **Packs** (report
packs, exported to PDF), **Published**, **Data feeds** and **Dashboards**.

![Reports → Dashboards: a board drawn inside the Glass](images/user/08-reports-dashboard.png)

**Dashboards** draws the deployment's boards inside the Glass, showing only those you may open. The
same boards are at `bi.` in front of the deployment's address, signed in the same way.

![A report pack holding an open alert, a trend over alerts and a closed alert](images/user/21-alerts-in-reporting.png)

### 9.1 Alerts in a report pack

In **Packs**, under **Add an item**, choose **Alert** and then one of the alerts of the case's queue
that you can see (each listed by severity, status and what it found). The pack keeps the alert as it
was when you added it:

- what it found, in words, its kind, its severity and when it was raised;
- the entities it matched, and its evidence: the links and transactions it cites;
- whether it was still open: an open alert says "Open: not yet decided when this was added";
- if it was closed, its closing reason (for example "Closed as True match") and the words given;
- "Inferred: no one has confirmed this match" until a person confirms it, by closing it as a True
  match. A match is never shown as confirmed on anyone's behalf.

**Refresh** reads the alert again, so an alert added while open can show how it was closed; the
earlier copy stays in the pack's history.

An alert item is marked at the highest marking of what it cites, and rests on every node, link and
transaction it cites. A reader who may not see all of them does not get the item, and is told only
that some items are not shown, never how many or which. The same sentence covers an item whose alert
has since been taken back for everyone: reverting the load that raised it (an administrator's task)
takes back the alert with the load, so its item is not shown to anyone, its adder included. Exporting
checks each item again for the
person exporting; someone who may see none of it is refused, and nothing is recorded.

### 9.2 Alert trends

In **Trends**, **What to count** offers **Events** or **Alerts**. An alert trend counts the alerts
raised each week or month that you may see. Split it by **rule** (each typology rule by its name,
hotlists together, monitors together), **typology**, **severity** or **outcome**, and narrow it with
up to five filters on the same fields. Alerts are counted, never summed. An alert on something you
cannot see is in no bar and no total. Save an alert trend and add it to a pack as any trend; it
is bounded in the same way (104 periods and 12 series), and past that you are asked to narrow it.

### 9.3 The monitoring dashboard

The figures dashboards read now include monitoring figures for every kind of alert: alerts raised
per week by rule, alerts closed per week by outcome, how long alerts took to close, and hotlist
matches per week. They are counted as the dashboard's own account may see them, case by case. A
hotlist kept "only me" is counted for its owner alone, so it never appears on a shared board. An
administrator sets the board up (administration guide §12).

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
| Canvas | Arrows | Step to the next or previous neighbour; a screen reader hears its name, type and links |
| Canvas | Ctrl/Cmd+Arrows | Step within the selection; with Shift, through every node |
| Canvas | Space | Add or remove the focused node from the selection |
| Canvas | Enter | Expand the focused node, or read a document |
| Canvas | `\` | The focused node's or the selected link's menu |
| Canvas | `L`, Shift+`L` | The next or previous link of the focused node |
| Canvas | `G` | Fold or unfold the focused node's group |
| Canvas | `F` | Fit the graph to the view |
| Canvas | Shift+Arrows | Move the selection; with Alt, further |
| Canvas | Delete | Hide the selected link, or remove the selection from view |
| Matrix | Arrows, Home, End | Move between cells; with Ctrl, Home and End go to the first and last cell |
| Matrix | Page Down, Page Up | The next or previous page of rows |
| Matrix | Enter | Select the row's node or link |
| Matrix | Space | Add the row's node to the selection, or take it out |
| Anywhere | Esc | Clear the selection; close a menu, drawer or reader |
| Forms | Ctrl/Cmd+Enter | Confirm a reason, save a change or a note, ask a question |
| Side panels | Alt+Up, Alt+Down | Move a panel up or down the column |

Every action in the Glass can be reached from the keyboard. Panning, zooming and the lasso are by
pointer only, by design: the arrows, Space and `F` do the same work from the keyboard.
