// Home after sign-in (ADR-115 E3 and decision 7; `design/handoff/OspreyFlow Home.dc.html`): every
// signed-in person's landing with no case open. All three places for everyone, a place the person
// cannot use dimmed with the role it needs; only the first usable place's button in brass (DESIGN.md
// §3.2: one primary action in a region); G, I and A open them from anywhere on the page. Its figures
// are `homeData.ts`'s, each counted as the reader. The tiles are a convenience, never the gate.
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ROLES } from "../admin/AdminPlace";
import { MeshMark } from "../shell/BrandMark";
import { ClassificationStrip } from "../shell/ClassificationStrip";
import { homePanels } from "../rights/visibility";
import type { StartPlace } from "../rights/visibility";
import { whenLabel, type Fact, type HomeSummary, type Place } from "./homeData";
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
  person: HomePerson;
  /** `null` while the figures are being read. */
  summary: HomeSummary | null;
  onChoose: (place: StartPlace) => void;
  /** Opens a case, in the Glass or the Studio. */
  onOpenCase: (id: string, place: "glass" | "ingest") => void;
  account: ReactNode;
  marking: string | null;
  now?: Date;
}

const PANELS: Record<StartPlace, { title: string; who: string; what: string; key: string }> = {
  glass: { title: "Glass", who: "For analysts", key: "G",
           what: "Work a case on the graph, map and timeline. Record assessments with their evidence, and build trends and report packs." },
  ingest: { title: "Ingest Studio", who: "For data engineers", key: "I",
            what: "Draw pipelines from source to load over the domain model. Each transform is tested, and nothing is scripted." },
  admin: { title: "Admin console", who: "For administrators", key: "A",
           what: "Manage people, roles and dashboard identities, and watch the services. The console never reads case content." },
}; // prettier-ignore

const APP: Record<Place, string> = { glass: "Glass", ingest: "Ingest Studio", admin: "Admin console" };
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
          <span className={`home-pic__state home-glyph--${s.ok ? "ok" : "error"}`}>{s.ok ? "healthy" : "not answering"}</span>
        </div>
      ))}
    </div>
  );
}

export function HomePage({ rights, person, summary, onChoose, onOpenCase, account, marking, now = new Date() }: HomePageProps) {
  const panels = useMemo(() => homePanels(rights), [rights]);
  const allowed = useMemo(() => new Set(panels.filter((p) => p.allowed).map((p) => p.place)), [panels]);
  const primary = panels.find((p) => p.allowed)?.place;
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

  const facts = (place: StartPlace) => (summary ? (place === "glass" ? summary.glass : place === "ingest" ? summary.studio : summary.admin) : null);
  const attention = summary ? summary.attention.filter((a) => allowed.has(a.place)) : [];
  const current = TIPS[((tip % TIPS.length) + TIPS.length) % TIPS.length]!;

  return (
    <div className="home">
      {marking && <ClassificationStrip marking={marking} />}
      <header className="home-header">
        <MeshMark size={24} />
        <span className="home-header__wordmark"><b>Osprey</b>Flow</span>
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

        <div className="home-panels">
          {panels.map(({ place, allowed: usable, role }) => {
            const p = PANELS[place];
            const shown = facts(place);
            return (
              <section key={place} aria-label={p.title} className={`home-panel${usable ? "" : " home-panel--gated"}`}>
                <div className={`home-panel__picture${place === "glass" ? " network-canvas" : ""}`}>
                  {place === "glass" && <GlassPicture />}
                  {place === "ingest" && <StudioPicture held={usable ? (summary?.held ?? null) : null} />}
                  {place === "admin" && <AdminPicture services={usable ? (summary?.services ?? null) : null} />}
                </div>
                <div className="home-panel__body">
                  <div className="home-panel__head">
                    <h2>{p.title}</h2>
                    <span className="home-panel__who">{p.who}</span>
                  </div>
                  <p className="home-panel__what">{p.what}</p>
                  {usable && (shown ? <Facts facts={shown} /> : <p className="home-panel__reading">Reading…</p>)}
                  <span className="home-panel__spacer" />
                  {usable ? (
                    <button type="button" className={`btn${place === primary ? " btn--primary" : ""} home-panel__open`}
                            onClick={() => onChoose(place)}>
                      Open {p.title} <kbd className="home-key">{p.key}</kbd>
                    </button>
                  ) : (
                    <p className="home-panel__gate">You need the {role} role for this. Ask an administrator to add it.</p>
                  )}
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
                    <button type="button" className="home-attention__row"
                            onClick={() => (a.caseId && a.place !== "admin" ? onOpenCase(a.caseId, a.place) : onChoose(a.place))}>
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
                  </li>
                ))}
              </ul>
            </section>

            <section className="home-section">
              <div className="home-section__head">
                <h2 id="recent-cases">Recent cases</h2>
              </div>
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
