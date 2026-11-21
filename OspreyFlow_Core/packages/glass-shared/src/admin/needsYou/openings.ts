// Where an entry of *Needs you* opens (L2.7): Admin › Operations for an overdue promotion, the
// Studio's Model tab for proposed link types. The place is opened by its owner (App); the section or
// tab inside it is asked for here, so neither the shell nor the Studio needs a new prop threaded
// through. A request waits until the place that takes it is drawn, then is taken once. It is kept in
// the session too, since opening the Studio on another case reloads the page (`openCase`).
//
// Plain TypeScript: where the request is kept between pages is handed in by `bindOpeningsStorage`, so
// this file touches no browser object. The Glass binds the tab's own storage in
// `apps/workspace/src/admin/needsYou/openings.ts`; with nothing bound a request is kept in memory only.
export type Opening =
  | { kind: "admin"; section: string }
  | { kind: "studio"; tab: "model"; datasetId: string };

const KEY = "osprey.needsYou.opening";
const listeners = new Set<() => void>();

/** What a request is kept in between pages: the three calls of the browser's `Storage` that it uses. */
export interface OpeningsStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** Looked up at each use, as the browser's own was: nothing, until a place binds one. */
let storage: () => OpeningsStorage | null = () => null;

function stored(): Opening[] {
  try {
    const raw = storage()?.getItem(KEY);
    return raw ? (JSON.parse(raw) as Opening[]) : [];
  } catch {
    return [];
  }
}

function store(openings: Opening[]): void {
  try {
    if (openings.length === 0) storage()?.removeItem(KEY);
    else storage()?.setItem(KEY, JSON.stringify(openings));
  } catch {
    // No session storage: the request still holds until this page is left.
  }
}

let waiting: Opening[] = stored();

/** Keeps requests in `open()`'s storage from now on, and takes up any it already holds (a request left by the
 * page before a reload). Called once, by the place that owns a browser tab. */
export function bindOpeningsStorage(open: () => OpeningsStorage | null): void {
  storage = open;
  waiting = stored();
}

export function requestOpening(opening: Opening): void {
  waiting = [...waiting.filter((w) => w.kind !== opening.kind), opening];
  store(waiting);
  for (const listener of listeners) listener();
}

/** The waiting request of this kind, left waiting: a place takes it only when it is the one asked
 * for (the Studio open on another dataset leaves it for the reload into the right one). */
export function peekOpening<K extends Opening["kind"]>(kind: K): Extract<Opening, { kind: K }> | null {
  return (waiting.find((w) => w.kind === kind) as Extract<Opening, { kind: K }> | undefined) ?? null;
}

/** Takes the waiting request of this kind, if any (so it opens once). */
export function takeOpening<K extends Opening["kind"]>(
  kind: K,
): Extract<Opening, { kind: K }> | null {
  const found = waiting.find((w) => w.kind === kind) as
    Extract<Opening, { kind: K }> | undefined;
  if (!found) return null;
  waiting = waiting.filter((w) => w !== found);
  store(waiting);
  return found;
}

export function onOpening(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
