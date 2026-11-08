// The workspace's router (ADR-146 decision 6): an alert has an address, `/alerts/<id>`, that Home,
// the queue, a board, the canvas and an email all open; and Rules and Monitoring has one, `/rules`,
// so a case can be opened on it (a case switch reloads the page). The rest of the workspace keeps
// its state as before; only these are paths. No dependency: the History API, and `popstate` for Back
// and Forward. The server already answers every path with the workspace (`nginx.conf.template`'s
// `try_files … /index.html`).
//
// The address grants nothing: the alert is asked for from the Conduit (`GET /v1/alerts/{id}`), which
// answers an alert the reader may not see exactly as one that does not exist (rule 3).
//
// Sign-in returns to the workspace's root (`auth/oidcConfig.ts`'s `redirectUri`), so an address
// opened while signed out is noted in this tab's session storage first and taken back after.
import { useSyncExternalStore } from "react";

export type Address = { kind: "alert"; alertId: string } | { kind: "rules" } | { kind: "none" };

const ALERT_PATH = /^\/alerts\/([^/]+)\/?$/;
export const RULES_PATH = "/rules";
export const ADDRESS_NOTE_KEY = "ospreyflow.address";

/** What a path addresses. */
export function parseAddress(pathname: string): Address {
  if (pathname === RULES_PATH || pathname === `${RULES_PATH}/`) return { kind: "rules" };
  const found = ALERT_PATH.exec(pathname);
  if (!found) return { kind: "none" };
  try {
    return { kind: "alert", alertId: decodeURIComponent(found[1]!) };
  } catch {
    return { kind: "none" };
  }
}

/** An alert's address. */
export function alertPath(alertId: string): string {
  return `/alerts/${encodeURIComponent(alertId)}`;
}

/** Goes to `path`, as a new entry (Back returns) or in place of this one. */
export function navigate(path: string, options: { replace?: boolean } = {}): void {
  const target = path + (path === "/" ? window.location.search : "");
  if (options.replace) window.history.replaceState(null, "", target);
  else window.history.pushState(null, "", target);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  return () => window.removeEventListener("popstate", onChange);
}

const pathname = () => window.location.pathname;

/** The address on screen, kept current through Back, Forward and `navigate`. */
export function useAddress(): Address {
  const path = useSyncExternalStore(subscribe, pathname, () => "/");
  return parseAddress(path);
}

/** Notes the address on screen, so the sign-in round trip, which returns to the root, keeps it. */
export function noteAddress(location: Pick<Location, "pathname"> = window.location, storage: Storage = sessionStorage): void {
  if (parseAddress(location.pathname).kind === "none") return;
  try {
    storage.setItem(ADDRESS_NOTE_KEY, location.pathname);
  } catch {
    /* a tab that refuses storage loses the address over sign-in, and lands on Home */
  }
}

/** The address noted before sign-in, once; the note is then cleared. Only an address this router
 * reads is taken back: anything else in the note is dropped. */
export function takeNotedAddress(storage: Storage = sessionStorage): string | null {
  let noted: string | null = null;
  try {
    noted = storage.getItem(ADDRESS_NOTE_KEY);
    storage.removeItem(ADDRESS_NOTE_KEY);
  } catch {
    return null;
  }
  return noted && parseAddress(noted).kind !== "none" ? noted : null;
}
