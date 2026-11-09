// Home after sign-in (ADR-115 E3 and decision 7; `design/handoff/OspreyFlow Home.dc.html`): every
// signed-in person's landing with no case open. ADR-145 decision 1 and N6: a card for each place the
// person's rights open, the same list as the place switcher, and none for a place they cannot open
// (this replaces ADR-115 decision 7's dimmed panels). Only the first card's button in brass (DESIGN.md
// §3.2: one primary action in a region); G, I and A open them from anywhere on the page. Its figures
// are `homeData.ts`'s, each counted as the reader. The tiles are a convenience, never the gate.
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ROLES } from "../admin/AdminPlace";
import { currentBrand } from "../brand/brand";
import { MeshMark } from "../shell/BrandMark";
import { ClassificationStrip } from "../shell/ClassificationStrip";
import { PLACE_KEY, PLACE_NAME } from "../shell/places";
import { startPlaces } from "../rights/visibility";
import type { StartPlace } from "../rights/visibility";
import { whenLabel, type AttentionRow, type Fact, type HomeSummary, type Place } from "./homeData";
import { TIPS, TipPicture } from "./tips";
import "./home.css";

export interface HomePerson {
  username: string;
  givenName?: string | null;
  clearance: string;
  roles: string[];
}

export interface HomePageProps {
  rights: ReadonlySet<string>;
  /** The rights could not be read, so no place is offered (ADR-145 N6): Home says so. */
  rightsUnread?: boolean;
  person: HomePerson;
  /** `null` while the figures are being read. */
  summary: HomeSummary | null;
  onChoose: (place: StartPlace) => void;
  /** Opens a case, in the Glass or the Studio. */
  onOpenCase: (id: string, place: "glass" | "ingest") => void;
  /** Opens an alert at its address, in Rules and Monitoring (ADR-146 decision 6: Home opens the
   * alert, not the case). */
  onOpenAlert?: (alertId: string) => void;
  /** The Reports Viewer's journey (ADR-145 Amendment 4 decision 10): for a reader Rules and Monitoring
   * is not offered to, an alert's row offers *Open in its case* (its Figures) and *Open the dashboard*
   * (the Alert monitoring board), never the alert itself. */
  onAlertJourney?: (alert: AlertJourneyStart, to: "figures" | "board") => void;
  account: ReactNode;
  marking: string | null;
  now?: Date;
  /** ADR-145 Amendment 4 decision 12 (L2.7): *What you can do, and what you answer for*, drawn by
   * App from the person's own reads (`home/AnswersForSection.tsx`). */
  answers?: ReactNode;
}

// The cards' names and keys are the places' table's (`shell/places.json`); what each holds is Home's.
const WORDS: Record<StartPlace, { who: string; what: string }> = {
  glass: { who: "For analysts",
           what: "Work a case on the graph, map and timeline. Record assessments with their evidence, and build trends and report packs." },
  ingest: { who: "For data engineers",
            what: "Draw pipelines from source to load over the domain model. Each transform is tested, and nothing is scripted." },
  rules: { who: "For analysts and rule authors",
           what: "Work the alerts that rules and watches raise, in one queue, and see what raises them." },
  admin: { who: "For administrators",
           what: "Manage people, roles and dashboard identities, and watch the services. The console never reads case content." },
}; // prettier-ignore
const PANELS = Object.fromEntries(
  (Object.keys(WORDS) as StartPlace[]).map((place) => [place, { ...WORDS[place], title: PLACE_NAME[place], key: PLACE_KEY[place] }]),
) as Record<StartPlace, { title: string; who: string; what: string; key: string }>;

const APP: Record<Place, string> = { glass: "Glass", ingest: "Ingest Studio", rules: "Rules and Monitoring", admin: "Admin area" };
const GLYPH: Record<Fact["tone"], string> = { ok: "✓", warn: "△", error: "!", info: "·" };

function greeting(now: Date): string {
  const hour = now.getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function roleList(roles: string[]): string {
  const names = ROLES.filter((r) => roles.includes(r.id)).map((r) => r.label);
  if (names.length === 0) return "none yet";
  return names.length === 1 ? names[0]! : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function Facts({ facts }: { facts: Fact[] }) {
  return (
    <ul className="home-facts">
      {facts.map((f) => (
        <li key={f.text}>
          <span className={`home-glyph home-glyph--${f.tone}`} aria-hidden="true">{GLYPH[f.tone]}</span>
          <span>{f.text}</span>
        </li>
      ))}
    </ul>
  );
}

function GlassPicture() {
  return (
    <svg viewBox="0 0 320 132" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <g className="home-pic__edge">
        <line x1="70" y1="40" x2="128" y2="66" /><line x1="58" y1="92" x2="128" y2="66" /><line x1="128" y1="66" x2="186" y2="44" />
        <line x1="186" y1="44" x2="246" y2="34" /><line x1="186" y1="44" x2="238" y2="92" /><line x1="128" y1="66" x2="160" y2="104" />
        <line x1="238" y1="92" x2="282" y2="70" /><line x1="246" y1="34" x2="282" y2="70" strokeDasharray="4 3" /><line x1="96" y1="26" x2="70" y2="40" />
      </g>
      <g className="home-pic__path"><line x1="58" y1="92" x2="128" y2="66" /><line x1="128" y1="66" x2="186" y2="44" /><line x1="186" y1="44" x2="238" y2="92" /></g>
      <circle cx="70" cy="40" r="6" style={{ fill: "var(--ch-indigo)" }} /><circle cx="58" cy="92" r="6" style={{ fill: "var(--ch-indigo)" }} />
      <circle cx="96" cy="26" r="5" style={{ fill: "var(--ch-indigo)" }} /><rect x="121" y="59" width="14" height="14" style={{ fill: "var(--ch-azure)" }} />
      <path d="M186 36L194 44L186 52L178 44Z" style={{ fill: "var(--ch-violet)" }} />
      <rect x="240" y="28" width="12" height="12" rx="3" style={{ fill: "var(--ch-jade)" }} /><rect x="232" y="86" width="12" height="12" rx="3" style={{ fill: "var(--ch-jade)" }} />
      <path d="M282 64a6 6 0 1 0 .01 0ZM282 67.5a2.5 2.5 0 1 1-.01 0Z" fillRule="evenodd" style={{ fill: "var(--ch-ochre)" }} />
      <circle cx="160" cy="104" r="5" style={{ fill: "var(--ch-indigo)" }} />
      <circle cx="128" cy="66" r="12" className="home-pic__selected" />
    </svg>
  ); // prettier-ignore
}

function StudioPicture({ held }: { held: number | null }) {
  const stages = ["Source", "Profile", "Map", "Load"];
  return (
    <div className="home-pic__pipeline" aria-hidden="true">
      {stages.map((stage, i) => (
        <div key={stage} className="home-pic__step">
          <div className="home-pic__stage-box">
            <div className={`home-pic__stage${stage === "Load" && held ? " home-pic__stage--held" : ""}`}>{stage}</div>
            {stage === "Load" && held ? <span className="value home-pic__held">△ {held} held</span> : <span className="home-pic__meta" />}
          </div>
          {i < stages.length - 1 && (
            <svg width="22" height="10" viewBox="0 0 22 10" className="home-pic__arrow">
              <path d="M1 5h18M15 1.5L19 5l-4 3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </div>
      ))}
    </div>
  );
}

function AdminPicture({ services }: { services: HomeSummary["services"] }) {
  if (!services) return <div className="home-pic__note">Each service, asked when the console opens.</div>;
  return (
    <div className="home-pic__services" aria-hidden="true">
      {services.map((s) => (
        <div key={s.name} className="home-pic__service">
          <span className={`home-glyph home-glyph--${s.ok ? "ok" : "error"}`}>{s.ok ? "✓" : "!"}</span>
          <span className="value home-pic__service-name">{s.name}</span>
          <span className="home-pic__rule" />
          <span className={`home-pic__state home-glyph--${s.ok ? "ok" : "error"}`}>{s.ok ? "healthy" : s.notice ? "needs attention" : "not answering"}</span>
        </div>
      ))}
    </div>
  );
}

/** Rules and Monitoring's picture: the alerts waiting for the reader, as a figure. */
function RulesPicture({ open }: { open: number | null }) {
  return (
    <div className="home-pic__pipeline home-pic--rules" aria-hidden="true">
      <span className="value home-pic__figure">{open === null ? "…" : open.toLocaleString("en-GB")}</span>
      <span className="home-pic__caption">{open === 1 ? "alert waiting for you" : "alerts waiting for you"}</span>
    </div>
  );
}

/** Where an alert row on the Reports Viewer's Home leads from (ADR-145 Amendment 4 decision 10). */
export interface AlertJourneyStart {
  caseId: string;
  alertId: string;
  /** The row's title, which the journey's banner names the alert by. */
  title: string;
  rule: { label: string; typology: string };
  at: string;
}

/** A Reports Viewer's alert row: the alert in words, and the two ways on, to the case's Figures and
 * to the board behind it. It never opens the alert. */
function JourneyRow({ row, now, onJourney }: { row: AttentionRow; now: Date; onJourney: (to: "figures" | "board") => void }) {
  return (
    <div className="home-attention__row" role="group" aria-label={row.title}>
      <span className={`home-glyph home-glyph--${row.tone}`} aria-hidden="true">{GLYPH[row.tone]}</span>
      <span className="home-attention__text">
        <span className="home-attention__title">{row.title}</span>
        <span className="home-attention__detail">{row.detail}</span>
        <span style={{ display: "flex", gap: "var(--sp-8)", marginTop: "var(--sp-4)", flexWrap: "wrap" }}>
          <button type="button" className="btn" onClick={() => onJourney("figures")}>Open in its case</button>
          <button type="button" className="btn" onClick={() => onJourney("board")}>Open the dashboard</button>
        </span>
      </span>
      <span className="home-attention__meta">
        <span className="home-tag">{APP[row.place]}</span>
        <span className="value">{whenLabel(row.at, now)}</span>
      </span>
    </div>
  );
}

export function HomePage({ rights, rightsUnread = false, person, summary, onChoose, onOpenCase, onOpenAlert, onAlertJourney, account, marking, now = new Date(), answers }: HomePageProps) {
  const panels = useMemo(() => startPlaces(rights), [rights]);
  const allowed = useMemo(() => new Set(panels), [panels]);
  const primary = panels[0];
  const [tip, setTip] = useState(0);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const place = (Object.keys(PANELS) as StartPlace[]).find((p) => PANELS[p].key.toLowerCase() === event.key.toLowerCase());
      if (place && allowed.has(place)) onChoose(place);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [allowed, onChoose]);

  // Someone whose rights read the queue but do not open Rules and Monitoring (a Reports Viewer) keeps
  // the alerts on the Glass's card, each row opening its case, as before ADR-146.
  const alertsInGlass = !allowed.has("rules") && allowed.has("glass");
  const facts = (place: StartPlace) =>
    summary
      ? place === "glass"
        ? [...summary.glass, ...(alertsInGlass ? summary.rules : [])]
        : place === "rules"
          ? summary.rules
          : place === "ingest"
            ? summary.studio
            : summary.admin
      : null;
  const attention = summary
    ? summary.attention
        .map((a) => (a.place === "rules" && alertsInGlass ? { ...a, place: "glass" as const, alertId: undefined, journeyAlertId: a.alertId } : a))
        .filter((a) => allowed.has(a.place))
    : [];
  const noCases = summary !== null && summary.recent.length === 0;
  const current = TIPS[((tip % TIPS.length) + TIPS.length) % TIPS.length]!;

  return (
    <div className="home">
      {marking && <ClassificationStrip marking={marking} />}
      <header className="home-header">
        {/* ADR-132: under GOV.UK the GOV.UK header stands above and the page title names the service; no OspreyFlow mark. */}
        {currentBrand() !== "govuk" && (
          <>
            <MeshMark size={24} />
            <span className="home-header__wordmark"><b>Osprey</b>Flow</span>
          </>
        )}
        <span className="home-header__spacer" />
        {account}
      </header>
      <main className="home-main">
        <section className="home-greeting">
          <h1>
            {greeting(now)}, {person.givenName || person.username}
          </h1>
          <p>
            Signed in as <span className="value">{person.username}</span> with clearance{" "}
            <span className="value">{person.clearance || "none"}</span>. Your roles: {roleList(person.roles)}.
          </p>
        </section>

        {panels.length === 0 && (
          <p className="home-section__empty">
            {rightsUnread
              ? "What your account may open could not be read just now, so no place is offered. Sign in again, or try again shortly."
              : "Your account opens no place yet. Ask an administrator to give you a role."}
          </p>
        )}
        <div className="home-panels">
          {panels.map((place) => {
            const p = PANELS[place];
            const shown = facts(place);
            return (
              <section key={place} aria-label={p.title} className="home-panel">
                <div className={`home-panel__picture${place === "glass" ? " network-canvas" : ""}`}>
                  {place === "glass" && <GlassPicture />}
                  {place === "ingest" && <StudioPicture held={summary?.held ?? null} />}
                  {place === "rules" && <RulesPicture open={summary ? summary.attention.filter((a) => a.place === "rules").length : null} />}
                  {place === "admin" && <AdminPicture services={summary?.services ?? null} />}
                </div>
                <div className="home-panel__body">
                  <div className="home-panel__head">
                    <h2>{p.title}</h2>
                    <span className="home-panel__who">{p.who}</span>
                  </div>
                  <p className="home-panel__what">{p.what}</p>
                  {shown ? <Facts facts={shown} /> : <p className="home-panel__reading">Reading…</p>}
                  <span className="home-panel__spacer" />
                  <button type="button" className={`btn${place === primary ? " btn--primary" : ""} home-panel__open`}
                          onClick={() => onChoose(place)}>
                    Open {p.title} <kbd className="home-key">{p.key}</kbd>
                  </button>
                </div>
              </section>
            );
          })}
        </div>

        <div className="home-columns">
          <div className="home-column">
            <section aria-label="Needs your attention" className="home-section">
              <div className="home-section__head">
                <h2>Needs your attention</h2>
                <span className="value home-section__count">{attention.length === 1 ? "1 item" : `${attention.length} items`}</span>
              </div>
              {summary && attention.length === 0 && <p className="home-section__empty">Nothing needs you now.</p>}
              <ul className="home-attention">
                {attention.map((a) => (
                  <li key={`${a.place}-${a.title}-${a.at}`}>
                    {"journeyAlertId" in a && a.journeyAlertId && a.caseId && a.alertRule && onAlertJourney ? (
                      <JourneyRow row={a} now={now} onJourney={(to) =>
                        onAlertJourney({ caseId: a.caseId!, alertId: a.journeyAlertId!, title: a.title, rule: a.alertRule!, at: a.at }, to)} />
                    ) : (
                    <button type="button" className="home-attention__row"
                            onClick={() =>
                              a.alertId && onOpenAlert
                                ? onOpenAlert(a.alertId)
                                : a.caseId && (a.place === "glass" || a.place === "ingest")
                                  ? onOpenCase(a.caseId, a.place)
                                  : onChoose(a.place)
                            }>
                      <span className={`home-glyph home-glyph--${a.tone}`} aria-hidden="true">{GLYPH[a.tone]}</span>
                      <span className="home-attention__text">
                        <span className="home-attention__title">{a.title}</span>
                        <span className="home-attention__detail">{a.detail}</span>
                      </span>
                      <span className="home-attention__meta">
                        <span className="home-tag">{APP[a.place]}</span>
                        <span className="value">{whenLabel(a.at, now)}</span>
                      </span>
                    </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
            {answers}

            <section className="home-section">
              <div className="home-section__head">
                <h2 id="recent-cases">Recent cases</h2>
              </div>
              {/* ADR-099 Amendment 11: a person with no role, or no case yet, is told so in words rather
                  than shown an empty table. */}
              {noCases ? (
                <p className="home-section__empty">No cases to show.</p>
              ) : (
                <table className="home-cases" aria-labelledby="recent-cases">
                  <thead>
                    <tr><th scope="col">Case</th><th scope="col">Your level</th><th scope="col" className="numeric">Entities</th><th scope="col">Created</th></tr>
                  </thead>
                  <tbody>
                    {(summary?.recent ?? []).slice(0, 6).map((c) => (
                      <tr key={c.id}>
                        <td>
                          {allowed.has("glass") ? (
                            <button type="button" className="home-cases__open" onClick={() => onOpenCase(c.id, "glass")}>{c.name}</button>
                          ) : c.name}
                        </td>
                        <td>{c.level}</td>
                        <td className="numeric"><span className="value">{c.entities === null ? "—" : c.entities.toLocaleString("en-GB")}</span></td>
                        <td><span className="value">{whenLabel(c.created, now)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>

          <div className="home-column">
            <section aria-label="Ways of working" className="home-section">
              <div className="home-section__head">
                <h2>Ways of working</h2>
                <span className="home-tips__nav">
                  <span className="value home-section__count">{`${TIPS.indexOf(current) + 1} of ${TIPS.length}`}</span>
                  <button type="button" className="btn home-tips__step" aria-label="Previous way of working" onClick={() => setTip((t) => t - 1)}>‹</button>
                  <button type="button" className="btn home-tips__step" aria-label="Next way of working" onClick={() => setTip((t) => t + 1)}>›</button>
                </span>
              </div>
              <div className="home-tip" aria-live="polite">
                <div className="home-tip__picture"><TipPicture kind={current.kind} /></div>
                <div className="home-tip__body">
                  <div className="home-tip__head">
                    <h3>{current.title}</h3>
                    <span className="home-tag">{current.app}</span>
                  </div>
                  <p>{current.says}</p>
                </div>
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
