# DRAFT: Accessibility statement for [service name]

> **DRAFT, not for publication.** Prepared on 2 November 2026 by the OspreyFlow build (GDS re-audit,
> build order step 9b), following GOV.UK's sample accessibility statement
> (`https://www.gov.uk/government/publications/sample-accessibility-statement`). Everything in square
> brackets is for the organisation running the service to fill in.
>
> **No independent accessibility audit has been done yet; one is planned** (remediation plan A9).
> This draft rests on the product team's own automated and manual checks, which are listed under
> "Preparation of this accessibility statement". It must be revised after that audit, and its
> compliance status set from the audit's findings, before it is published. It makes no claim that the
> service is compliant with WCAG 2.2 or the accessibility regulations.
>
> The product's own page, `apps/workspace/public/accessibility-statement.html`, is still a placeholder
> (remediation A10); this draft is what it will be built from.

This accessibility statement applies to [service name], at [https://service-domain.gov.uk], an
intelligence analysis service built on OspreyFlow. It covers the analyst workspace (the Glass: the
network graph, the Matrix view, the map, the timeline, reports, Monitoring), the Ingest Studio, the
Admin area and the sign-in page. It does not cover the dashboards at [bi.service-domain.gov.uk], which
are a separate product (Apache Superset) with their own look.

This service is run by [organisation]. We want as many people as possible to be able to use it. For
example, that means you should be able to:

- change colours, contrast levels and fonts using browser or device settings (the service has a light
  and a dark theme);
- zoom in up to 400% without the text spilling off the screen (checked so far at a 320 pixel width on
  the start page, the sign-in page and the GOV.UK page frame; see "Parts not yet checked");
- navigate most of the service using just a keyboard, including every action on the network graph;
- navigate most of the service using speech recognition software;
- listen to most of the service using a screen reader, including the network as tables (the Matrix
  view).

We have also made the text as simple as we can.

[AbilityNet](https://mcmw.abilitynet.org.uk/) has advice on making your device easier to use if you
have a disability.

## How accessible this service is

We know some parts of this service are not fully accessible:

- the map does not yet list the places it plots as text, so a screen reader user cannot read where
  things are on it;
- the timeline's histogram of activity over time is not yet available as a table of counts;
- the network graph is a drawn picture: a screen reader user hears the name, type and number of links
  of the node in focus, and can read the same network as two tables in the Matrix view, but the
  picture's layout (which nodes are drawn close together) has no text equivalent;
- the guided install page labels one button "Map" but heads the screen it opens "Geospatial";
- the dashboards have not been checked at all.

## Feedback and contact information

If you need information on this service in a different format, such as accessible PDF, large print,
easy read, audio recording or braille:

- email [accessibility contact email address]
- call [phone number]
- [any other contact route, such as a text relay service]

We'll consider your request and get back to you in [number] days.

## Reporting accessibility problems with this service

We're always looking to improve the accessibility of this service. If you find any problems not
listed on this page, or think we're not meeting accessibility requirements, contact [name of the
team, email address and phone number]. Tell us the page or screen, what you were trying to do, and
the browser and any assistive technology you use. We aim to reply within [number] working days.

## Enforcement procedure

The Equality and Human Rights Commission (EHRC) is responsible for enforcing the Public Sector Bodies
(Websites and Mobile Applications) (No. 2) Accessibility Regulations 2018 (the "accessibility
regulations"). If you're not happy with how we respond to your complaint,
[contact the Equality Advisory and Support Service (EASS)](https://www.equalityadvisoryservice.com/).

[For a service in Northern Ireland: the Equality Commission for Northern Ireland (ECNI).]

## Technical information about this service's accessibility

[Organisation] is committed to making its service accessible, in accordance with the Public Sector
Bodies (Websites and Mobile Applications) (No. 2) Accessibility Regulations 2018.

### Compliance status

**To be set after the independent audit.** On the product team's own evidence, the expected status
is that this service is *partially compliant* with the
[Web Content Accessibility Guidelines version 2.2](https://www.w3.org/TR/WCAG22/) AA standard, due to
the non-compliances listed below. The independent audit may find more.

## Non-accessible content

The content listed below is non-accessible for the following reasons.

### Non-compliance with the accessibility regulations

1. **The map** (the Map view) shows located people, places and events as markers with no text
   alternative listing them. This fails WCAG 2.2 success criterion 1.1.1 (Non-text content) and
   1.3.1 (Info and relationships). Partial alternatives today: the Matrix view lists the same
   working set as tables, and the Inspector gives the details of a selected item, but neither gives
   its place or coordinates. We plan a list of the located items beside the map, each selecting its
   marker (remediation A4).
2. **The timeline's histogram** shows activity over time as bars; its controls are named and reachable
   by keyboard, but the counts in each bar are not available as text. This fails 1.1.1 (Non-text
   content). We plan a "Show as table" option (remediation A5).
3. **The network graph's layout** conveys clusters and distance by position. A screen reader user hears
   the focused node's name, type and link count, and can read every node and link in the Matrix view,
   but the clustering itself has no text equivalent. We are assessing whether this fails 1.3.1, or is
   adequately met by the Matrix view as an equivalent alternative; the independent audit will decide.
4. **The guided install page** names a navigation button "Map" and the screen it opens "Geospatial".
   This may fail 2.4.6 (Headings and labels) and is a consistency problem (remediation A13). The page is
   used once, by the administrator installing the service.

Fixed since the first audit (1 November 2026), each with an automated test that failed before the fix:
the start page's text contrast in a closed panel (1.4.3), the sign-in page's language (3.1.1), focus
landing inside a folded timeline (2.4.3, 4.1.2), two sets of button names (2.5.3), the start page's
reflow at 320 pixels (1.4.10), a tap target under 24 pixels (2.5.8), the absence of a table view of the
network (the Matrix view, 1.3.1), the canvas not saying which node has focus (4.1.2), and, on
2 November 2026, fourteen form fields in Monitoring, the Ingest Studio, Admin and Ownership whose
spoken names did not contain their visible labels (2.5.3 Label in name).

### Disproportionate burden

We are not claiming disproportionate burden for any part of this service.

### Content that's not within the scope of the accessibility regulations

[To be completed by the organisation: for example, PDFs or other documents published before
23 September 2018 that are not essential to providing the service, or live recordings.]

## Parts not yet checked

These have not been checked by anyone yet, so problems there are not listed above:

- **Testing with assistive technology.** No testing with JAWS, NVDA, VoiceOver, TalkBack, Dragon or
  screen magnification has been done. Everything above comes from automated scans and from reading
  the code and driving the screens by keyboard.
- **The dashboards** at [bi.service-domain.gov.uk] (Apache Superset).
- **Zoom to 400% and text spacing** (1.4.4, 1.4.12) on the whole service. Reflow at a 320 pixel width
  is checked automatically on the start page, the sign-in page and the GOV.UK page frame only.
- **The service under the GOV.UK look, screen by screen.** 14 of the 42 screens the product's automated
  scan covers are also checked under the GOV.UK look; the other 28 are checked in the product's own
  look only (remediation A6).
- **The live service.** The automated scans of the newest screens (Monitoring's queue, rules, sentence
  builder, lists and watches; the close and approval forms; Checks on load and Verify) run against
  test pages that mount the real screens with invented data, not against a running deployment
  (remediation A8).
- **Documents the service produces:** exported report packs, and the PDF user and administration guides.
- **Mobile and touch use.** The workspace is designed for a desktop; no mobile device has been tested.

## What we're doing to improve accessibility

The product's specification makes WCAG 2.2 AA a floor, and every change to it is checked
automatically: axe-core at WCAG 2.0, 2.1 and 2.2 A and AA on every screen's test page in both themes
(and under the GOV.UK look where the page applies it), a check that every labelled form field's spoken
name contains its visible label, a reflow check at 320 pixels, a 24 pixel minimum tap target, and a
keyboard test for every action on the network graph. Our remediation plan
(`process/gds/gds_remediation_plan.md`) lists, in priority order: a text list for the map (A4), a table
for the timeline (A5), the GOV.UK look checked on every screen (A6), repeatable scans of a running
deployment (A8), GOV.UK form patterns such as the error summary (A11), and 400% zoom and text spacing
checks (A12). **An independent WCAG 2.2 AA audit with assistive technology testing is planned (A9)**,
and this statement will be revised from its findings.

## Preparation of this accessibility statement

This statement was prepared on 2 November 2026. It has not yet been reviewed. [It was last reviewed on
[date].]

This service was last tested on 2 November 2026, by the product team, not by an independent auditor.
The tests were:

- automated axe-core scans (WCAG 2.0, 2.1 and 2.2, A and AA) of 42 test pages that each mount a real
  screen, and of 15 further states drawn on them (143 scans in all), and of the guided install page's
  9 screens and its starter choices (22 scans), in the dark and light themes;
- an automated check that each labelled form field's accessible name contains its visible label (57
  pages and states);
- an automated reflow check at 320 pixels, and an automated 24 pixel target check;
- 487 automated keyboard tests;
- a manual review, by reading the code and driving the screens by keyboard, of the network graph, the
  map, the timeline, and the screens added since the first audit: Monitoring (the queue, the rules and
  the sentence builder, the lists and the watches, closing an alert and approving a close or a rule
  change), Checks on load and Verify in the Ingest Studio, and the starter choice on the guided
  install page.

We chose these because the network graph, map and timeline are the hardest parts of the service to
make accessible, and the Monitoring and Ingest Studio screens were new since the first audit of
1 November 2026. [After the independent audit: "We used [auditor's] audit of [date], which tested a
sample of [pages] chosen by [method]."]
