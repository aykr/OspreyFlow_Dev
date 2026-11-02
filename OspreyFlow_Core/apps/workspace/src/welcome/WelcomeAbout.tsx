// The welcome page's About (ADR-115 decision 8; Amendment 4): what the product is for, with screens of
// synthetic demonstration cases. Switched off by `welcome.about: false`.
import { currentBrand } from "../brand/brand";
import { MeshMark } from "../shell/BrandMark";
import { PRODUCT_STATEMENT } from "./statement";
import amlDecision from "./assets/screen-aml-decision.jpg";
import amlOwnership from "./assets/screen-aml-ownership.jpg";
import amlQueue from "./assets/screen-aml-queue.jpg";
import communities from "./assets/screen-communities.jpg";
import structuringRing from "./assets/screen-structuring-ring.jpg";
import timelineCyclical from "./assets/screen-timeline-cyclical.jpg";

interface Feature {
  picture: string;
  alt: string;
  title: string;
  body: string;
}

const CRIME: Feature[] = [
  { picture: structuringRing, alt: "The graph canvas with communities boxed and a broker between them",
    title: "Structure found, not drawn by hand",
    body: "Community detection finds the groups, and centrality finds the brokers who join them. Every expansion shows how much it will draw before drawing it, and an expansion over the working-set limit is refused with options. Nothing is cut silently." },
  { picture: timelineCyclical, alt: "The timeline's cyclical view, a case folded onto one week",
    title: "When it happens",
    body: "Brushing the timeline dims everything outside the window, so the network stays where you left it. The cyclical view folds a case onto a single week to show its rhythm, such as calls in the evening after visits and none on a Sunday." },
  { picture: communities, alt: "Communities and centrality beside the canvas",
    title: "Who matters",
    body: "Communities and centrality appear beside the canvas, counted only over what this analyst may see. Betweenness finds the people who join two groups. Pick a ranked name and the canvas centres on them." },
]; // prettier-ignore

const LIFECYCLE = [
  { stage: "Prevent", what: "onboarding and KYC", says: "Applicants and their beneficial owners are screened as the file loads, before the customer goes live." },
  { stage: "Detect", what: "transaction monitoring", says: "Structuring, rapid movement and circular flow run as rules, before or after the data is committed." },
  { stage: "Investigate", what: "enhanced due diligence", says: "Ownership is traced through every layer, and risk is read factor by factor and across the neighbourhood." },
  { stage: "Report", what: "decision and record", says: "Every alert is closed with a reason, and every rule decision is audited." },
]; // prettier-ignore

const AML: Feature[] = [
  { picture: amlQueue, alt: "The alert queue, each alert naming its typology",
    title: "The queue says what fired",
    body: "Alerts are raised as the data loads, before it is committed. Each one names its typology and explains itself in a sentence. A screening match is a suggestion until a person confirms it." },
  { picture: amlOwnership, alt: "Beneficial ownership traced through layers, each share as arithmetic",
    title: "Who stands behind the applicant",
    body: "Cumulative beneficial ownership is traced through every layer, and circles of cross-holdings are traced only once. Each share is shown as arithmetic, for example 60% × 80% = 48%, so an auditor can redo it by hand." },
  { picture: amlDecision, alt: "An alert being closed with a reason",
    title: "A person decides",
    body: "Closing an alert needs a reason from a closed list (True match, False positive, Duplicate, No further action, Referred) and words. A true match confirms both the alert and the match it found, which is the only way model-inferred data is promoted. Who decided, when and why stays with the alert." },
]; // prettier-ignore

// ADR-115 Amendment 4: fraud detection and event monitoring, in words; the screens above serve both.
const FRAUD = [
  { title: "Rings that share an identity", says: "Applicants, accounts and claims that share a phone number, an address or an account are drawn together, so a ring reads as one cluster, not a dozen unrelated cases." },
  { title: "Patterns as rules", says: "Structuring, rapid movement and circular flow run as typology rules on every load, and each alert names the rule that raised it." },
  { title: "One person, many records", says: "Records that look like the same person are scored as a match and read as one, never merged in storage, so a wrong match can be undone." },
]; // prettier-ignore

const MONITORING = [
  { title: "Hotlists and watches", says: "Put a number, an account or a person on a hotlist with a review date. When a load matches it, an alert says what matched, and which file and row put it there." },
  { title: "Rules on every load", says: "Typology rules run as the data arrives, before it is committed, and their alerts land in one queue for the team." },
  { title: "Each alert explains itself", says: "An alert names its rule or hotlist entry, the entity it matched and its evidence. It is closed with a reason, and the reason stays on the record." },
]; // prettier-ignore

const SAFEGUARDS = [
  { title: "Filtered in the store", says: "A record you may not see is absent, and so is any count or path that would reveal it." },
  { title: "Handling travels with the data", says: "Classification is set when data is ingested and is checked again, item by item, at export." },
  { title: "Every read and write is recorded", says: "Each read carries the person who made it, and each write is added to an audit trail." },
  { title: "Runs where your data lives", says: "It is open source throughout, runs air-gapped, and uses the same images from a laptop to a cluster." },
]; // prettier-ignore

function Points({ points, label }: { points: { title: string; says: string }[]; label: string }) {
  return (
    <dl aria-label={label} className="welcome-safeguards__list welcome-points">
      {points.map((p) => (
        <div key={p.title}>
          <dt>{p.title}</dt>
          <dd>{p.says}</dd>
        </div>
      ))}
    </dl>
  );
}

function Features({ features }: { features: Feature[] }) {
  return (
    <div className="welcome-features">
      {features.map((f) => (
        <article key={f.title} className="welcome-feature">
          <div className="welcome-feature__picture">
            <img src={f.picture} alt={f.alt} loading="lazy" />
          </div>
          <div>
            <h4 className="welcome-feature__title">{f.title}</h4>
            <p className="welcome-feature__body">{f.body}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

export function WelcomeAbout({ version = null }: { version?: string | null }) {
  return (
    <section id="about" className="welcome-about">
      <div className="welcome-section">
        {/* ADR-132 Amendment 4: under GOV.UK the product's identity is here, not in the page's chrome. */}
        {currentBrand() === "govuk" && (
          <section aria-labelledby="about-ospreyflow" className="welcome-identity">
            <MeshMark size={40} />
            <div>
              <h2 id="about-ospreyflow" className="welcome-identity__title">About OspreyFlow</h2>
              <p className="welcome-about__sub">
                {PRODUCT_STATEMENT} This service is built on it.
                {version && <> Version <span className="value">{version}</span>.</>}
              </p>
            </div>
          </section>
        )}
        <h2 className="welcome-about__title">One intelligence map</h2>
        <p className="welcome-about__lead">
          {/* ADR-034 Amendment 1: under GOV.UK the statement is in the identity block above. */}
          {currentBrand() !== "govuk" && <>{PRODUCT_STATEMENT} </>}
          Crime analysis, anti-money-laundering and fraud detection use the same graph, rules and reports, and event
          monitoring watches all of it as new data arrives. The screens below come from synthetic demonstration cases.
        </p>
        <h3 className="welcome-about__heading">Crime analysis</h3>
        <p className="welcome-about__sub">For fraud and organised-crime analysts: networks, rhythm, and the people who matter.</p>
        <Features features={CRIME} />
        <div className="welcome-about__part">
          <h3 className="welcome-about__heading">Anti-money-laundering</h3>
          <p className="welcome-about__sub">
            For financial-crime teams: from onboarding to a decision on the record. The same rules work at each stage.
          </p>
          <ol aria-label="Financial-crime lifecycle" className="welcome-lifecycle">
            {LIFECYCLE.map((s) => (
              <li key={s.stage}>
                <div className="welcome-lifecycle__stage">
                  <span>{s.stage}</span>
                  <span className="welcome-lifecycle__what">{s.what}</span>
                </div>
                <p>{s.says}</p>
              </li>
            ))}
          </ol>
          <Features features={AML} />
        </div>
        <div className="welcome-about__part">
          <h3 className="welcome-about__heading">Fraud detection</h3>
          <p className="welcome-about__sub">For counter-fraud teams: the rings behind the claims and applications.</p>
          <Points points={FRAUD} label="Fraud detection" />
        </div>
        <div className="welcome-about__part">
          <h3 className="welcome-about__heading">Event monitoring and alerting</h3>
          <p className="welcome-about__sub">For every team: the graph watches new data, so a match finds you.</p>
          <Points points={MONITORING} label="Event monitoring and alerting" />
        </div>
        <div className="welcome-about__part welcome-safeguards">
          <div>
            <h2 className="welcome-safeguards__title">Seeing is not doing</h2>
            <p className="welcome-about__sub">
              Control and audit are the conditions an analyst works within. They are not a check run at export.
            </p>
          </div>
          <dl className="welcome-safeguards__list">
            {SAFEGUARDS.map((s) => (
              <div key={s.title}>
                <dt>{s.title}</dt>
                <dd>{s.says}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
