// Light and dark (ADR-070). Dark is the working default (tokens.css); light is the separately tuned
// ramp already there under `[data-theme="light"]`. The choice is kept in this browser only: it is a
// way of looking at the page, so it is never sent to the server and is not part of the case.
//
// Everything drawn by CSS follows `data-theme` on its own. What is painted to a canvas (the graph,
// the timeline) cannot read a CSS variable, so it asks `currentTheme()` and listens with
// `onThemeChange()` to draw again.
export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "ospreyflow.theme";

const listeners = new Set<(theme: Theme) => void>();

/** The saved choice; dark when nothing is saved, the value is not recognised, or the browser will
 * not let the page read its storage (a private window, blocked site data). */
export function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function storeTheme(theme: Theme): void {
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
