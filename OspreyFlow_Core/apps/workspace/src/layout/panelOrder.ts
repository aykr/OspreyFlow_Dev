// The order of the right-hand column's panels (ADR-085).
//
// The analyst can put the Inspector, the Metrics panel and the Query builder in any order. The order
// is a way of looking, so it is kept in this browser only, never sent to the server and not part of
// the case: the standing the theme (ADR-070), the label choice (ADR-076) and the icon choice (ADR-079)
// have. Like them it is a small store that components subscribe to.
//
// A stored order can never lose or duplicate a panel: an id the Glass does not know is dropped, a
// panel the list lacks is appended in default order, and anything that is not a list of strings is
// read as the default.
import { useSyncExternalStore } from "react";

export const SIDE_PANEL_ORDER_KEY = "ospreyflow.side-panel-order";

/** The panels of the right-hand column, in their default order (ADR-082's layout). */
export const SIDE_PANEL_IDS = ["inspector", "metrics", "query-builder"] as const;

export type SidePanelId = (typeof SIDE_PANEL_IDS)[number];
export type SidePanelOrder = readonly SidePanelId[];

let cache: SidePanelOrder | null = null;
const listeners = new Set<() => void>();

function isSidePanelId(value: unknown): value is SidePanelId {
  return typeof value === "string" && (SIDE_PANEL_IDS as readonly string[]).includes(value);
}

/** Every known panel exactly once, in the stored order where it is usable and default order otherwise. */
export function normaliseSidePanelOrder(value: unknown): SidePanelId[] {
  const kept: SidePanelId[] = [];
  if (Array.isArray(value)) {
    for (const item of value) {
      if (isSidePanelId(item) && !kept.includes(item)) kept.push(item);
    }
  }
  for (const id of SIDE_PANEL_IDS) {
    if (!kept.includes(id)) kept.push(id);
  }
  return kept;
}

function load(): SidePanelOrder {
  if (cache === null) {
    let raw: string | null = null;
    try {
      raw = localStorage.getItem(SIDE_PANEL_ORDER_KEY);
    } catch {
      // A private window or blocked site data: the order then lasts for this page only.
    }
    let parsed: unknown = null;
    if (raw !== null) {
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = null;
      }
    }
    cache = normaliseSidePanelOrder(parsed);
  }
  return cache;
}

/** The order now in force. */
export function getSidePanelOrder(): SidePanelOrder {
  return load();
}

function store(next: SidePanelId[]): void {
  cache = next;
  try {
    localStorage.setItem(SIDE_PANEL_ORDER_KEY, JSON.stringify(next));
  } catch {
    // Kept in memory for this page, which is the honest fallback.
  }
  listeners.forEach((listener) => listener());
}

function sameOrder(a: SidePanelOrder, b: SidePanelOrder): boolean {
  return a.length === b.length && a.every((id, i) => id === b[i]);
}

/** Swaps `id` with its neighbour above or below. At the end of the stack nothing changes. */
export function moveSidePanel(id: SidePanelId, direction: "up" | "down"): void {
  const before = load();
  const from = before.indexOf(id);
  const to = direction === "up" ? from - 1 : from + 1;
  const neighbour = before[to];
  if (from < 0 || neighbour === undefined) return;
  const next = [...before];
  next[from] = neighbour;
  next[to] = id;
  store(next);
}

/**
 * Puts `id` in `target`'s slot (a drop): the dragged panel takes the target's position in the stack
 * and the panels between them shift toward the gap it left, so dropping on the bottom panel puts the
 * dragged panel at the bottom and dropping on the top panel puts it at the top.
 */
export function moveSidePanelTo(id: SidePanelId, target: SidePanelId): void {
  const before = load();
  const to = before.indexOf(target);
  if (id === target || to < 0 || !before.includes(id)) return;
  const next = before.filter((other) => other !== id);
  next.splice(to, 0, id);
  if (sameOrder(next, before)) return;
  store(next);
}

/** Calls `listener` whenever the order changes. Returns the function that stops it. */
export function onSidePanelOrderChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The order, re-rendering the caller when it changes. */
export function useSidePanelOrder(): SidePanelOrder {
  return useSyncExternalStore(onSidePanelOrderChange, getSidePanelOrder, getSidePanelOrder);
}

/** Forgets what was read, so the next read comes from storage again. For tests. */
export function forgetSidePanelOrderForTest(): void {
  cache = null;
  listeners.clear();
}
