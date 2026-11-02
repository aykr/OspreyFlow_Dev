# GDS pitch deck: content for seven slides

Build order step 9b, 2 November 2026. The content for a short deck on OspreyFlow and the GOV.UK
Service Standard (Gemini's brief: title, the mission, Service Standard alignment, accessibility,
security by design, deployment, the road to assessment). It feeds step 10 (a GDS section in the
Product Overview deck) and step 12 (the website).

**Wording rules for every slide (the owner, 1 November 2026):**

- Say "designed to meet the GDS Service Standard". Never "GDS-compliant", "WCAG-compliant",
  "accredited" or "assured": only a service assessment panel decides whether a service meets the
  Standard, and it assesses a service (a team running a product for its users), not a product alone.
- The independent accessibility audit, the penetration test and the DPIA are **planned**, and are
  always listed as planned.
- Every claim below is evidenced in `gds_compliance_report.md` (the 9b re-audit, section 8). Claim
  nothing that report does not evidence.

---

## Slide 1: Title

**Title:** OspreyFlow for the UK public sector

**Subtitle:** Intelligence analysis and network discovery, designed to meet the GDS Service Standard

**Strap line:** Open source. Accessible by design. Secure in the data layer. Yours to run.

**Footer:** Apache-2.0 · 2 November 2026

**Speaker notes:** OspreyFlow is an open-source platform for intelligence analysis: loading sources,
finding the people, places and links in them, and monitoring for what changes. This deck is about one
question a department asks before it buys anything: can a service built on it pass a GDS service
assessment? Our answer is that it is designed to meet the Service Standard, and here is the evidence;
the assessment itself is the department's, and three independent checks are still to come.

---

## Slide 2: The mission

**Title:** Analysts should spend their time on judgement, not on plumbing

**Points:**

- One case, from loading the sources to an assessed report: the Ingest Studio, the network graph, the
  map, the timeline and report packs in one product
- Monitoring and alerting built in: rules written as plain sentences, sanctions and watch lists
  re-screened as they change, one alert queue, and a second person for the decisions that matter
- Every finding keeps where it came from; anything a model suggests stays "inferred" until a person
  confirms it
- Open source and open standards, so a department is never locked in to a supplier

**Speaker notes:** The analyst's problem is rarely a lack of data. It is the work around it: getting
sources in, keeping track of what came from where, noticing when something changes, and writing it
up for someone who has to act. OspreyFlow puts that in one place. Monitoring is a core part of it,
not an add-on: a rule can be written as a sentence ("a person on a sanctions list who sends more than
£10,000 within 30 days"), previewed against the last 90 days before it goes live, and closing a
high-severity alert takes a second person.

---

## Slide 3: Service Standard alignment

**Title:** Designed to meet the GDS Service Standard: the evidence, point by point

**Table (point, status, evidence):**

| Point | Status | Evidence |
| --- | --- | --- |
| 2 Solve a whole problem | Met in the product | One case from source to report; monitoring feeds the same case |
| 5 Everyone can use it | Partly | WCAG 2.2 AA as a floor; automated scans of every screen; the Matrix view; independent audit planned |
| 8 Iterate and improve | Met in the product | Signed releases; updates that verify and roll back |
| 9 Secure and private | Partly | Access control inside every query; secrets owner-only; OpenAPI behind sign-in; penetration test and DPIA planned |
| 11 Right tools | Met | Open stack chosen by recorded decision; four typed ports with conformance suites |
| 12 Open source | Met | Apache-2.0; a licence gate fails the build |
| 13 Open standards | Partly | OpenID Connect, OpenAPI 3.1 (published and versioned), STIX 2.1, vector tiles, Parquet; GOV.UK Design System preset |
| 14 Reliable service | Met in the product | Health checks, backup and restore, three deployment modes |
| 1, 6, 7, 10 | The service team's | The product supports them; user research, the team, governance and published KPIs are the department's |

**Footnote:** "Met" means the product's own evidence for what it can show is in the repository, named.
It is not an assessment result. Points 3 and 4 are partly met (dashboards keep their own look;
usability testing is the service team's).

**Speaker notes:** Read the status column honestly. Four points are about the people running the
service, and no product can meet them on a department's behalf. Of the rest, the product carries its
own evidence: a named test, decision record or command for each claim, collected in a re-audit of the
finished product on 2 November 2026.

---

## Slide 4: Accessibility

**Title:** Accessible by design, and tested on every change

**Points:**

- WCAG 2.2 AA is a floor in the specification, not a target
- Every screen is scanned automatically for WCAG 2.0, 2.1 and 2.2 A and AA issues, in both themes and
  under the GOV.UK look where it applies: 143 scans of 42 screens and their states, plus 22 of the
  guided install page
- Every action on the network graph is reachable by keyboard, each proven by its own test (487
  keyboard tests)
- The network as tables a screen reader can walk (the Matrix view), and the graph says which node has
  focus
- Colour never carries meaning alone: nine entity types, each with its own shape
- **Planned:** an independent WCAG 2.2 AA audit with assistive-technology testing (JAWS, NVDA,
  VoiceOver, TalkBack, Dragon, magnification), and the accessibility statement published from it

**Known gaps, said plainly:** the map does not yet list its places as text, and the timeline's counts
are not yet a table.

**Speaker notes:** A network graph on a canvas is the hardest thing to make accessible, so it was
treated as the design problem from the start. The re-audit found and fixed one more class of defect
automated tools miss: fourteen form fields whose spoken name did not match the words on screen, which
matters to people using speech recognition. A draft accessibility statement lists the known issues
and the parts not yet checked. Automated tools find only part of what WCAG asks, which is why the
independent audit is planned.

---

## Slide 5: Security by design

**Title:** Secure in the data layer, not just on the screen

**Points:**

- Sign-in by OpenID Connect with PKCE against the department's own identity provider; no password
  enters the product
- Clearance, unit and handling codes are applied inside every database query, so a hidden record
  cannot be inferred from a count, a path length or a chart
- Nothing leaves a deployment by default; a hosted model is used only if an administrator enables it,
  for datasets marked sendable
- A second person approves a whole-deployment rule and the close of a high-severity alert
- Secrets are readable by their owner alone; the API's description is published only behind sign-in
- Static analysis, dependency, secret and configuration scans triaged in the re-audit; releases signed
- **Planned:** a penetration test (CHECK or CREST), a DPIA, and a software bill of materials per release

**Speaker notes:** The access rule lives in the store adapter, and the conformance suites test the
three ways a hidden record can leak: a count, a path and a histogram bucket. The re-audit found one
thing to tighten: the one-computer mode (Lite) answers on every network interface, not on the
computer alone, so it must never be opened to a network; Small and Enterprise serve HTTPS.

---

## Slide 6: Deployment

**Title:** One product, three ways to run it, and a start in minutes

**Points:**

- **Lite:** one computer, for a pilot or a demonstration; plain HTTP on `localhost`, never opened to a
  network
- **Small:** one cloud server on AWS or Azure in a UK region, with managed PostgreSQL and object
  storage, HTTPS with a certificate obtained and renewed automatically
- **Enterprise:** a Kubernetes cluster (EKS or AKS), the same product as replicas
- **Starters:** choose a theme and a domain at install (`ospreyflow install --starter govuk-crime`):
  themes OspreyFlow and GOV.UK; domains crime, anti-money laundering, fraud, cyber, or blank
- **The GOV.UK theme:** header, footer, crown, GDS Transport, phase banner and the service's own name,
  a deployment setting rather than a fork; a gov.uk service is served over HTTPS (Small or Enterprise)
- Several deployments side by side on one machine, each with its own folder, address and data

**Speaker notes:** A department can see the product in its own GOV.UK look on day one: the GOV.UK
starter asks for the service's name, organisation and phase, and fills in the rest. The GOV.UK look is
for gov.uk domains, and a gov.uk service is served over HTTPS, so outside a demonstration that means
Small or Enterprise.

---

## Slide 7: The road to assessment

**Title:** The road to a service assessment

**Done:**

- Baseline audit against all 14 points (1 November 2026), with seven defects fixed, each proven by a
  test that failed first
- Re-audit of the finished product, monitoring included (2 November 2026), with the evidence pack
  updated and a draft accessibility statement

**Planned (to be commissioned by the department or the supplier):**

- An independent WCAG 2.2 AA accessibility audit with assistive-technology testing
- A penetration test (CHECK or CREST)
- A data protection impact assessment (DPIA), from a template the product will provide

**Then, the service team's:**

- User research with the department's analysts, and usability testing
- The team, governance and published performance measures (points 1, 6, 7 and 10)
- An alpha, beta and live assessment by a GDS or departmental panel

**Closing line:** Designed to meet the GDS Service Standard; assessed by the people whose job it is.

**Speaker notes:** Be exact about what is done and what is not. The product's own evidence is in a
folder an assessor can read. The three independent checks are planned, not done, and the assessment
itself belongs to the service team that runs it.
