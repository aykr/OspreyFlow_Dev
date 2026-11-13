# The Glass's navigation and the search results layout (the owner's decision, 13 November 2026)

Saved verbatim in substance from the owner's message of 13 Nov evening. Parts A and B are decided and start on receipt.
C, D and E wait for the orchestrator's estimates and the owner's answer. The owner's order if something must give:
**A, B, D without "Whole case", C, E, then D's "Whole case"**. Nothing is dropped from that order without asking.

**The one rule behind the design.** Every job has exactly one control:
- everything that replaces the main area is in one view switch;
- the left rail only opens panels beside the current view;
- there is one route to cases, and one place to manage saved views.

**Rules that still apply:**
- Both looks: GOV.UK Design System components in the GOV.UK look, and `a11y/every-harness.spec.ts` and the keyboard
  specs updated for every change.
- Tests first. Synthetic data only.
- `OspreyFlow_Core/Makefile` and `.github/` changes go to the owner as diffs.
- The GOV.UK header and wordmark on the gated demo stay as they are.
- Do not repeat the four screen fixes already sent; Part B replaces one of them.

## Part A · Search results layout (v0.5.2, start now: step 3e′)

Results fill the main area of the Glass; they are not a side panel.

| Element | What it does |
|---|---|
| Back link | "Back to Graph" (or whichever view the person left). Returns to that view exactly as it was. A GOV.UK back link in the GOV.UK look |
| Heading | "Search results for '…'", with the total, announced to screen readers when results load |
| Groups | By type, with counts (All, People, Documents…). Choosing a group filters the list |
| Filters | The filters the search service offers, beside the list |
| Each result | Name or title, type, and why it matched. Documents show the highlighted passage |
| Actions | "Show on graph" for every result. "Open" for documents |
| Ask link | One line at the end of the list: "Ask a question about '…' instead". It opens Ask & Chat with the words carried over. Nothing is sent to a model until the person presses Ask |
| No results | Says so, and offers the Ask link and a way to clear filters |
| Search unavailable | When the fallback to today's search is in use, one line says the results are limited |

- **Suggestions:** suggestions under the box stay as they are. Enter opens the results page.
- **Leaving the results:** while results show, no view-switch entry is current. The back link is the way out, and
  choosing any view also leaves the results.
- **Access:** counts, groups and passages obey the access rules (the search design's section 6).
- **Focus:** it moves to the results heading on open, and back to the search box on "Back".

## Part B · Navigation (v0.5.2, start now: folded into step 3e)

**The view switch** is one group in the top bar, in this order:

| Button | What it opens |
|---|---|
| Graph | The case's graph |
| Map | The map |
| Drawing board | The drawing boards |
| Reports | Today's Dashboards view, unchanged inside (Alert monitoring first, then the Superset boards) |
| More views | Matrix, Figures, Ownership, Connection strength |

- "Reports" is the on-screen name for today's Dashboards view. "Figures" keeps its name, under More views.
- Exactly one view is current at any time.
- Remove the Graph · Drawing board links from the strip, and the note under them. The drawing board's own screen
  still says a board is a sketch that does not change the case's data.

**The left rail** holds only entries that open a panel: Explore, Ask & Chat and History, then Help and the show-names
toggle.
- Remove Cases, Dashboards and "Explore Details".
- Opening or closing a panel never changes the view.
- Closing returns focus to the entry that opened it.

**The case line** reads: **You are in the Glass · Case [switcher] · Views in this case · reads …**
- The word "Case" is visible before the switcher.
- The switcher's last entry is "All cases", which opens today's Cases panel.
- "Views in this case" is a button that opens the same panel at its views list (open, share, delete).
- The graph toolbar's "Views" menu (ADR-144 Am 3) stays.

**The fix already sent:** step 3e's "the strip says Graph: the case's data while the page shows Alert monitoring, and
two rail items are marked at once" is replaced by Part B. The other three fixes stand.

**Amendments:** ADR-145 Amendment 13 (the modes in the strip, and the note) is replaced. Amendments 12 (rail layout)
and 2 (More views) change. Each records the owner's decision of 13 Nov.

## Part C · One set of actions for the selection (estimate first)

- Right-click on a selected item shows actions for the whole selection: the same actions, and the same words, as the
  bottom bar.
- Right-click on an unselected item selects it first.
- The menu's heading says what it applies to: "2 selected", or the item's name.
- With one item selected, the menu also shows that item's own actions (links by type, Link to, Find paths to…).
- Link types with no links fold into one line ("7 types with no links").
- The menu never opens over the bottom bar.
- Every action is reachable by keyboard.

## Part D · Ask & Chat (estimate first; the owner wants all of it in v0.5.2)

**Read from:** a choice above the question box. The first option is the default when something is selected.
- **Selected items:** the items, their links and their documents.
- **Everything on the graph:** every item, link and document on the graph now.
- **Whole case:** what the case's datasets hold that the person may see. It is found by the search service from the
  question's words, takes the top visible results, and cites each one. It reuses the search access rules, and the
  leak test extends to it. It says in one line that it finds things by names and words. If it cannot be ready by the
  freeze, it shows as unavailable with the reason, and the owner is told before that is decided.

**No refusal for want of documents:**
- Remove the `no_documents` refusal. With no documents, the model answers from the links and events, and the answer
  says so.
- Before asking, the panel states what will be read ("Will read: 0 documents, 2 selected items and their links").
- Above the box: "About: Tarbuck, Kyle and 1 other", or "About: everything on the graph".
- The rules on what may leave for an outside model do not change.

**The model engine:**
- Always name the engine that will answer, even when there is only one.
- When other engines exist but cannot be used for this case, list them with the reason.
- If the engine list fails to load, say so, never "none".

**Amendments:** ADR-098 decision 4 (documents required), ADR-129 (what the brief is built from), ADR-135 decision 5 (the
picker hidden below two engines).

## Part E · Typeface (estimate first)

In the GOV.UK look, card headings ("Alerts", "Raised each week", "Team view") and the right-click menu's heading are in
a monospace face. Use the page's own face for headings, and keep monospace for identifiers and values only.

## Later, not in v0.5.2

- One box for both search and questions.
- Matrix as a "show as table" choice on the graph.
- Reports and Figures as one page.
- A report builder inside the Glass.

## The owner's six questions

1. Do A and B fit the case lane's two days? If not, what is the smallest part of B that must wait?
2. A "Build a report" link beside Reports, opening Superset for people with the right to build: is it small enough
   for v0.5.2?
3. On the GOV.UK demo, Ask & Chat shows no engine choice, though local models and Gemini are configured. Is Gemini not
   offered for this role, withheld for this case's data, or did the engine list fail to load?
4. On the same demo, principal.png was on the graph and Ask still said the case holds no document. Why was it not
   counted?
5. Is every right-click action reachable by keyboard today? If not, which are missing?
6. Does anything in A–E conflict with an ADR or the client page beyond the listed amendments?
