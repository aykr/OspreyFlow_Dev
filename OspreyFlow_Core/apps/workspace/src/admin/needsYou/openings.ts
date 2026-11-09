// Where an entry of *Needs you* opens (L2.7): Admin › Operations for an overdue promotion, the
// Studio's Model tab for proposed link types. The place is opened by its owner (App); the section or
// tab inside it is asked for here, so neither the shell nor the Studio needs a new prop threaded
// through. A request waits until the place that takes it is drawn, then is taken once. It is kept in
// the session too, since opening the Studio on another case reloads the page (`openCase`).
export type Opening =
  | { kind: "admin"; section: string }
  | { kind: "studio"; tab: "model"; datasetId: string };

const KEY = "osprey.needsYou.opening";
const listeners = new Set<() => void>();

function stored(): Opening[] {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Opening[]) : [];
  } catch {
    return [];
  }
}

function store(openings: Opening[]): void {
  try {
    if (openings.length === 0) sessionStorage.removeItem(KEY);
    else sessionStorage.setItem(KEY, JSON.stringify(openings));
  } catch {
    // No session storage: the request still holds until this page is left.
  }
}

let waiting: Opening[] = stored();

export function requestOpening(opening: Opening): void {
  waiting = [...waiting.filter((w) => w.kind !== opening.kind), opening];
  store(waiting);
  for (const listener of listeners) listener();
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
