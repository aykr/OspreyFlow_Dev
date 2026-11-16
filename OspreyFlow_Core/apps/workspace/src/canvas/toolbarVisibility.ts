// v0.6.1 glass-rows C (ADR-145 Amendment 19 decision 6; the owner's rulings 3 and 4, 16 November 2026): the toolbar
// above a view's canvas, the Graph's canvas tools or the Map's row, can be hidden. Whether it is hidden is remembered
// per signed-in analyst in this browser (`ospreyflow.glass.toolbar.<username>`, "hidden" or nothing), as the Studio
// remembers its mode (ADR-140 decision 3): one setting for the Graph and the Map, read before the first draw.
import { useCallback, useEffect, useRef, useSyncExternalStore, type RefObject } from "react";

export const toolbarKey = (username: string) => `ospreyflow.glass.toolbar.${username}`;

/** The toolbar's id while hidden or shown, which *Hide toolbar* and *Show toolbar* name in `aria-controls`. One view's
 * toolbar is drawn at a time, so the Graph's and the Map's share it. */
export const VIEW_TOOLBAR_ID = "glass-view-toolbar";

// What was set on this page, by key ("" for nobody signed in): it holds where nothing can be remembered (no username,
// or the browser's storage refused), so *Hide toolbar* always hides for the page even when it cannot be kept.
const thisPage = new Map<string, boolean>();

export function readToolbarHidden(username: string | null): boolean {
  const set = thisPage.get(username ?? "");
  if (set !== undefined) return set;
  if (!username) return false;
  try {
    return localStorage.getItem(toolbarKey(username)) === "hidden";
  } catch {
    return false;
  }
}

const listeners = new Set<() => void>();

export function writeToolbarHidden(username: string | null, hidden: boolean): void {
  thisPage.set(username ?? "", hidden);
  // Nobody signed in has nothing to remember it for.
  if (username) {
    try {
      if (hidden) localStorage.setItem(toolbarKey(username), "hidden");
      else localStorage.removeItem(toolbarKey(username));
    } catch {
      // A private window or blocked storage: not remembered, but hidden for this page.
    }
  }
  listeners.forEach((listener) => listener());
}

/** For tests: forget what was set on this page. */
export function forgetToolbarSettings(): void {
  thisPage.clear();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab of this browser hiding it changes this one's too, as the setting is the analyst's: what the
  // storage now says stands over what was set on this page.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && !event.key.startsWith("ospreyflow.glass.toolbar.")) return;
    thisPage.clear();
    listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Whether this analyst's toolbar is hidden, and a way to set it. Read during render, so the first draw is as left. */
export function useToolbarHidden(username: string | null): [boolean, (hidden: boolean) => void] {
  const hidden = useSyncExternalStore(subscribe, () => readToolbarHidden(username));
  const set = useCallback((next: boolean) => writeToolbarHidden(username, next), [username]);
  return [hidden, set];
}

/** The key that hides or shows the toolbar: T, with no modifier, while the graph's canvas has focus, as F, L and G are (the
 * owner's ruling of 16 November 2026, WCAG 2.1.4's "active only on focus"). Alt+Shift+T, first chosen, is Chrome's own
 * key on Windows and Linux for focusing its toolbar; no combination with a modifier was free in every browser and screen
 * reader. The sources are in the lane's build record. */
export function isToolbarKey(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "altKey" | "metaKey">): boolean {
  return (event.key === "t" || event.key === "T") && !event.ctrlKey && !event.altKey && !event.metaKey;
}

export const TOOLBAR_KEY = "T";

export interface ViewToolbar {
  /** Whether the toolbar is hidden here: never where the view has no such toolbar. */
  hidden: boolean;
  /** The buttons' toggle: focus moves to the other button. */
  toggle: () => void;
  /** The canvas's T: focus stays on the canvas, where the key was pressed and where nothing was lost. */
  toggleByKey: () => void;
  /** *Hide toolbar* and *Show toolbar*, for focus to move between them. */
  hideRef: RefObject<HTMLButtonElement | null>;
  showRef: RefObject<HTMLButtonElement | null>;
}

/**
 * The toolbar's hiding as App wires it (and the keyboard harness, with the same code): `here` is whether the view
 * on screen has a toolbar that can be hidden (the Graph and the Map, not the Drawing board, the owner's ruling 4; not
 * while a page lies over the view). Focus goes to *Show toolbar* on hiding and back to *Hide toolbar* on showing by
 * the buttons; the canvas's T leaves it on the canvas.
 */
export function useViewToolbar(username: string | null, here: boolean): ViewToolbar {
  const [setting, setSetting] = useToolbarHidden(username);
  const hidden = here && setting;
  const hideRef = useRef<HTMLButtonElement | null>(null);
  const showRef = useRef<HTMLButtonElement | null>(null);
  const focusRef = useRef<"hide" | "show" | null>(null);
  const toggle = useCallback(() => {
    focusRef.current = setting ? "hide" : "show";
    setSetting(!setting);
  }, [setting, setSetting]);
  // Only the canvas calls it, and the canvas is not drawn where the toolbar cannot be hidden (the Drawing board) and is
  // inert under a page over the view, so it needs no guard of its own.
  const toggleByKey = useCallback(() => {
    focusRef.current = null;
    setSetting(!setting);
  }, [setting, setSetting]);
  useEffect(() => {
    const which = focusRef.current;
    if (which === null) return;
    focusRef.current = null;
    (which === "show" ? showRef : hideRef).current?.focus();
  }, [hidden]);
  return { hidden, toggle, toggleByKey, hideRef, showRef };
}
