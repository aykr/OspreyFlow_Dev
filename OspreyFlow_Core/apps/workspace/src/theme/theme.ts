// Light and dark (ADR-070). Dark is the working default (tokens.css); light is the separately tuned
// ramp already there under `[data-theme="light"]`. The choice is kept in this browser only: it is a
// way of looking at the page, so it is never sent to the server and is not part of the case.
//
// It is kept in a cookie as well as in this page's storage (ADR-072). The pages of one deployment
// are on different names of one base (ADR-114 Amendment 4: the Glass, `id.` for the sign-in page,
// `bi.` for the dashboards), and a browser keeps a page's storage per origin, so the cookie, kept for
// the base name, is how a choice made on one page reaches the rest. The cookie holds only "light" or "dark" and is never read by a
// server. `harness/theme_cookie.js` is the same logic for the pages that are not React.
//
// Everything drawn by CSS follows `data-theme` on its own. What is painted to a canvas (the graph,
// the timeline) cannot read a CSS variable, so it asks `currentTheme()` and listens with
// `onThemeChange()` to draw again.
export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "ospreyflow.theme";
/** Shared by every page on this host; `harness/theme_cookie.js` uses the same name. */
export const THEME_COOKIE_NAME = "ospreyflow_theme";
const THEME_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 365;

const listeners = new Set<(theme: Theme) => void>();

function themeFrom(value: unknown): Theme | null {
  return value === "light" || value === "dark" ? value : null;
}

function readCookie(): Theme | null {
  try {
    const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${THEME_COOKIE_NAME}=([^;]*)`));
    return match ? themeFrom(match[1]) : null;
  } catch {
    return null;
  }
}

/** Where the choice is kept, so it reaches every name of the deployment (ADR-114 Amendment 4): the
 * Glass is at the base name, the sign-in page at `id.` and the dashboards at `bi.` in front of it,
 * so a page at either keeps it for the base. `localhost` and an address keep it for the host alone —
 * a browser takes no `Domain` there. `harness/theme_cookie.js` holds the same rule. */
export function themeCookieDomain(hostname: string): string | null {
  const host = hostname.toLowerCase().replace(/\.$/, "");
  if (!host.includes(".") || /^[\d.]+$/.test(host) || host.includes(":") || host.startsWith("[")) return null;
  return host.replace(/^(id|bi)\./, "");
}

/** The cookie assignments that keep `theme`: a copy kept for this host alone (as every page wrote it
 * before the names) is cleared first, so it can never shadow the shared one. */
export function themeCookieWrites(theme: Theme, hostname: string): string[] {
  const kept = `${THEME_COOKIE_NAME}=${theme}; Path=/; Max-Age=${THEME_COOKIE_MAX_AGE_S}; SameSite=Lax`;
  const domain = themeCookieDomain(hostname);
  return domain === null ? [kept] : [`${THEME_COOKIE_NAME}=; Path=/; Max-Age=0`, `${kept}; Domain=${domain}`];
}

function writeCookie(theme: Theme): void {
  try {
    for (const assignment of themeCookieWrites(theme, window.location.hostname)) document.cookie = assignment;
  } catch {
    // Without a cookie the choice still holds for this page, through its own storage.
  }
}

/** The saved choice; dark when nothing is saved, the value is not recognised, or the browser will
 * not let the page read its storage or cookies (a private window, blocked site data). The cookie
 * comes first, since another page may have changed it since this one last did. A choice found only
 * in this page's storage (made before the cookie existed) is put in the cookie, so the other pages
 * follow it too. */
export function readStoredTheme(): Theme {
  const shared = readCookie();
  if (shared) return shared;
  try {
    const stored = themeFrom(localStorage.getItem(THEME_STORAGE_KEY));
    if (stored) {
      writeCookie(stored);
      return stored;
    }
    return "dark";
  } catch {
    return "dark";
  }
}

export function storeTheme(theme: Theme): void {
  writeCookie(theme);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The choice then lasts only until the page is closed, which is the honest fallback.
  }
}

/** The theme the page is showing now. */
export function currentTheme(): Theme {
  // Dark where there is no page (a unit test of the arithmetic, a worker).
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

/** Shows `theme` and tells whatever is listening, if it changed. */
export function applyTheme(theme: Theme): void {
  const changed = currentTheme() !== theme || document.documentElement.getAttribute("data-theme") === null;
  document.documentElement.setAttribute("data-theme", theme);
  if (changed) listeners.forEach((listener) => listener(theme));
}

/** Calls `listener` whenever the theme changes. Returns the function that stops it. */
export function onThemeChange(listener: (theme: Theme) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
