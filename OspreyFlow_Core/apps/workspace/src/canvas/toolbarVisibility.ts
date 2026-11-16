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

/** Alt+Shift+T (Option+Shift+T on a Mac), matched by the key's place so the Option character does not matter. Not
 * Ctrl+Shift+T, a browser's reopen-tab; WCAG 2.1.4 leaves a key with a modifier free of a way to turn it off. */
export function isToolbarShortcut(event: KeyboardEvent): boolean {
  return event.code === "KeyT" && event.altKey && event.shiftKey && !event.ctrlKey && !event.metaKey;
}

export const TOOLBAR_SHORTCUT = "Alt+Shift+T";

// Inputs that take typed text; a checkbox, a slider or a button is not one, so the key works there (the lane-reviewer's
// item 11: every INPUT was refused, the strictness slider and the checkboxes too).
const TYPED = new Set(["text", "search", "email", "url", "tel", "password", "number", "date", "datetime-local", "month", "time", "week"]);

/** Whether a key pressed here is the field's own typing. */
export function isTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable || target.tagName === "TEXTAREA" || target.tagName === "SELECT") return true;
  return target instanceof HTMLInputElement && TYPED.has(target.type);
}

export interface ViewToolbar {
  /** Whether the toolbar is hidden here: never where the view has no such toolbar. */
  hidden: boolean;
  toggle: () => void;
  /** *Hide toolbar* and *Show toolbar*, for focus to move between them. */
  hideRef: RefObject<HTMLButtonElement | null>;
  showRef: RefObject<HTMLButtonElement | null>;
}

/**
 * The toolbar's hiding as App wires it (and the keyboard harness, with the same code): `here` is whether the view
 * on screen has a toolbar that can be hidden (the Graph and the Map; not the Drawing board, the owner's ruling 4).
 * Focus goes to *Show toolbar* on hiding and back to *Hide toolbar* on showing, by the button or the key alike;
 * Alt+Shift+T works outside text fields, as `?` does (`useHelpKey`).
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
  useEffect(() => {
    const which = focusRef.current;
    if (which === null) return;
    focusRef.current = null;
    (which === "show" ? showRef : hideRef).current?.focus();
  }, [hidden]);
  useEffect(() => {
    if (!here) return;
    const onKey = (event: KeyboardEvent) => {
      if (!isToolbarShortcut(event) || event.repeat) return;
      if (isTextField(event.target)) return;
      event.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [here, toggle]);
  return { hidden, toggle, hideRef, showRef };
}
