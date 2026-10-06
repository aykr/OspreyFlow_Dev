// Moving nodes by hand (owner, 6 October 2026): a drag moves the node, or the whole selection when
// the node is in it, by the pointer's movement; Shift with an arrow key nudges the selection; and a
// node the analyst placed stays there when a layout runs for nodes added later (Arrange lays out
// everything afresh). Kept apart from the canvas so it can be tested without a renderer.

type Point = { x: number; y: number };

/** The screen step of one nudge, in pixels; four times that with Alt. */
export const NUDGE_PX = 8;

/** Where each dragged node goes: its start position moved by the pointer's movement since the
 * drag began, all in graph coordinates. */
export function dragTargets(start: ReadonlyMap<string, Point>, from: Point, now: Point): Map<string, Point> {
  const dx = now.x - from.x;
  const dy = now.y - from.y;
  return new Map([...start].map(([id, at]) => [id, { x: at.x + dx, y: at.y + dy }]));
}

/** The screen step for a key pressed with Shift (and `large`, Alt), or `null` for any other key. */
export function nudgeFor(key: string, large: boolean): { dx: number; dy: number } | null {
  const step = large ? NUDGE_PX * 4 : NUDGE_PX;
  switch (key) {
    case "ArrowLeft":
      return { dx: -step, dy: 0 };
    case "ArrowRight":
      return { dx: step, dy: 0 };
    case "ArrowUp":
      return { dx: 0, dy: -step };
    case "ArrowDown":
      return { dx: 0, dy: step };
    default:
      return null;
  }
}

/** A layout's result with every pinned node kept where it is now. */
export function keepPinned(
  settled: ReadonlyMap<string, Point>,
  pinned: ReadonlySet<string>,
  currentOf: (id: string) => Point,
): Map<string, Point> {
  return new Map([...settled].map(([id, at]) => [id, pinned.has(id) ? currentOf(id) : at]));
}
