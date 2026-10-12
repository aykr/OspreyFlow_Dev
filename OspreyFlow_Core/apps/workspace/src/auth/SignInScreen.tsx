// `06_DECISIONS.md` ADR-050 — the sign-in screen, shown whenever there is no valid token
// (`spec/02_GLASS_FRONTEND.md` §2's "unauthenticated load"), and the surface a refused caller sees.
//
// ADR-115 (Phase E, stage E2): it is the welcome page of `design/handoff/OspreyFlow Welcome.dc.html`,
// rebuilt in the Glass's own components and tokens. The password is never typed here (decision 4):
// the card starts the OIDC code flow, and the email-or-username form, reset and "check your email"
// are Keycloak's own pages in the OspreyFlow login theme. Organisation sign-in appears only when the
// deployment names a brokered provider (decision 3); About and each footer link only as the
// deployment says (decision 8); the strip is the deployment's marking (decision 2).
import { useEffect, useState } from "react";

import { applyTheme, currentTheme, onThemeChange, storeTheme, type Theme } from "../theme/theme";
import { ClassificationStrip } from "../shell/ClassificationStrip";
import { MeshMark, SolidMark } from "../shell/BrandMark";
import { WelcomeAbout } from "../welcome/WelcomeAbout";
import { WelcomeFigure } from "../welcome/WelcomeFigure";
import type { WelcomeLink, WelcomeSettingsRead } from "./oidcConfig";
import "../welcome/welcome.css";

export type WelcomeSettings = WelcomeSettingsRead;

export interface SignInScreenProps {
  /** `00_ARCHITECTURE.md` §1.3's own distinction, carried to the Glass: *cannot reach the identity
   * provider* is a different statement from *the identity provider said no*, and a wrong-audience
   * token refused by the Conduit is a third — telling an analyst the wrong one of these is a false
   * and alarming statement about their own access. `null` means neither has happened yet (a plain,
   * first, unauthenticated load). */
  reason?: string | null;
  /** The launcher's Ingest Studio tile opens the Glass on its Ingest tab. If the sign-in has to be
   * done by hand, the card says which of the two the person is signing in to. */
  intent?: "ingest" | "questions" | "admin" | null;
  /** Starts the code flow; with an organisation's provider alias, straight to that provider. */
  onSignIn: (organisationProvider?: string) => void;
  /** The deployment's marking, in the strip above the page (ADR-115 decision 2). */
  marking?: string | null;
  welcome?: WelcomeSettings;
}

const PLAIN: WelcomeSettings = { organisationSignIn: null, about: true, links: {}, version: null };

const CAPABILITIES = [
  { name: "Network analysis", icon: "M4 4.5L11.5 6M4 4.5L6 12M11.5 6L6 12M3 3h2v3H3zM10.5 5h2v2h-2zM5 11h2v2H5z",
    says: "Expand, trace paths, find communities and the brokers between them." },
  { name: "Geospatial", icon: "M8 14.5s-4.5-4.6-4.5-8a4.5 4.5 0 0 1 9 0c0 3.4-4.5 8-4.5 8zM8 8a1.6 1.6 0 1 0 0-3.2A1.6 1.6 0 0 0 8 8z",
    says: "Places on a basemap served from your own deployment." },
  { name: "Timeline trends", icon: "M2 13.5h12M3.5 11V8M6.5 11V4.5M9.5 11V6.5M12.5 11V3",
    says: "Brush a window to dim what falls outside it, or fold a case onto one week." },
  { name: "Reporting", icon: "M4 2h6l3 3v9H4zM10 2v3h3M6 8.5h5M6 11h5",
    says: "Trends, assessments and notes in report packs, each item under its own marking." },
]; // prettier-ignore

const LINK_NAMES: [WelcomeLink, string][] = [
  ["account_help", "Account help"],
  ["accessibility", "Accessibility statement"],
  ["privacy", "Privacy notice"],
  ["service_status", "Service status"],
];

function ThemeButton() {
  const [theme, setTheme] = useState<Theme>(currentTheme());
  useEffect(() => onThemeChange(setTheme), []);
  const next: Theme = theme === "light" ? "dark" : "light";
  return (
    <button
      type="button"
      className="btn"
      onClick={() => {
        storeTheme(next);
        applyTheme(next);
      }}
    >
      {next === "light" ? "Light theme" : "Dark theme"}
    </button>
  );
}

function SignInCard({ reason, intent, onSignIn, welcome }: Required<Pick<SignInScreenProps, "onSignIn">> &
  Pick<SignInScreenProps, "reason" | "intent"> & { welcome: WelcomeSettings }) {  // prettier-ignore
  const [opening, setOpening] = useState<"organisation" | "account" | null>(null);
  const organisation = welcome.organisationSignIn;
  const help = welcome.links.account_help;
  const purpose =
    intent === "ingest"
      ? "Sign in to bring a new source of data in: connect it, map it, check it, publish it."
      : intent === "admin"
        ? "Sign in to administer this deployment."
        : "You see only what your role, clearance and cases allow. Every session is recorded in the audit log.";
  const start = (which: "organisation" | "account") => {
    setOpening(which);
    onSignIn(which === "organisation" && organisation ? organisation : undefined);
  };
  return (
    <aside className="welcome-card" aria-labelledby="signin-title">
      <div className="welcome-card__body">
        <div>
          <h2 id="signin-title" className="welcome-card__title">
            {intent === "ingest" ? "Sign in to the Ingest Studio" : intent === "admin" ? "Sign in to Admin" : "Sign in"}
          </h2>
          <p className="welcome-card__lead">{purpose}</p>
        </div>
        {reason && (
          <div role="alert" className="welcome-card__status">
            <span className="welcome-card__glyph" aria-hidden="true">!</span>
            <span>{reason}</span>
          </div>
        )}
        {organisation ? (
          <>
            <button type="button" className="btn btn--primary welcome-card__primary" disabled={opening !== null}
                    onClick={() => start("organisation")}>
              {opening === "organisation" ? "Opening your organisation's sign-in page…" : "Continue with organisation sign-in"}
            </button>
            <p className="welcome-card__note">Your password is entered only on your organisation's sign-in page.</p>
            <div className="welcome-card__divider"><span>or use an OspreyFlow account</span></div>
            <button type="button" className="btn welcome-card__secondary" disabled={opening !== null}
                    onClick={() => start("account")}>
              {opening === "account" ? "Opening the sign-in page…" : "Sign in with an OspreyFlow account"}
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn--primary welcome-card__primary" disabled={opening !== null}
                    onClick={() => start("account")}>
              {opening === "account" ? "Opening the sign-in page…" : "Sign in"}
            </button>
            <p className="welcome-card__note">Your password is entered only on the OspreyFlow sign-in page, never here.</p>
          </>
        )}
        <p className="welcome-card__foot">
          No account yet? Your OspreyFlow administrator invites people and assigns roles.
          {help && (
            <>
              {" "}Locked out or seeing the wrong cases? <a href={help}>Get account help</a>.
            </>
          )}
        </p>
      </div>
    </aside>
  );
} // prettier-ignore

export function SignInScreen({ reason, intent, onSignIn, marking = null, welcome = PLAIN }: SignInScreenProps) {
  return (
    <div className="welcome">
      {marking && <ClassificationStrip marking={marking} />}
      <header className="welcome-header">
        <span className="welcome-header__brand">
          <MeshMark size={28} />
          <span className="welcome-header__wordmark">
            <b>Osprey</b>Flow
          </span>
        </span>
        <nav aria-label="Page" className="welcome-header__nav">
          {welcome.about && <a href="#about">About</a>}
          <ThemeButton />
        </nav>
      </header>
      <main className="welcome-main">
        <section className="welcome-hero">
          <div className="welcome-hero__story">
            <div className="welcome-hero__intro">
              <h1 className="welcome-hero__title">Crime analysis on one graph</h1>
              <p className="welcome-hero__lead">
                Fraud, anti-money-laundering and organised-crime investigation in one workspace. Network, map, timeline
                and reports read the same case, and a filter applied in one view applies in all of them. Every element
                carries its handling and where it came from.
              </p>
            </div>
            <dl className="welcome-capabilities">
              {CAPABILITIES.map((c) => (
                <div key={c.name} className="welcome-capabilities__item">
                  <dt>
                    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
                      <path d={c.icon} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" />
                    </svg>
                    {c.name}
                  </dt>
                  <dd>{c.says}</dd>
                </div>
              ))}
            </dl>
            <WelcomeFigure />
          </div>
          <SignInCard reason={reason} intent={intent} onSignIn={onSignIn} welcome={welcome} />
        </section>
        {welcome.about && <WelcomeAbout />}
      </main>
      <footer className="welcome-footer">
        <div className="welcome-footer__brand">
          <SolidMark size={16} />
          <span>OspreyFlow</span>
          {welcome.version && <span className="value">{welcome.version}</span>}
        </div>
        <nav aria-label="Footer" className="welcome-footer__links">
          {LINK_NAMES.filter(([key]) => welcome.links[key]).map(([key, name]) => (
            <a key={key} href={welcome.links[key]}>
              {name}
            </a>
          ))}
        </nav>
      </footer>
    </div>
  );
}
