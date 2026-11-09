// What the board surface reads from an opened board, as pure functions (ADR-143 decisions 4 and 5):
// an item's name, whether it is drawn, where it sits, and how far an arrow key moves it. Tested in
// `boardModel.test.ts`; the surface itself in `keyboard/boards.spec.ts`.
import type { BoardOpened } from "./boardsApi";

export type BoardNode = BoardOpened["nodes"][number];
export type BoardEdge = BoardOpened["edges"][number];

export interface Position {
  x: number;
  y: number;
}

type SchemeGrades = { source: string[]; intelligence: string[]; handling: string[] };
const offered: Record<string, SchemeGrades> = {};
/** Before a board is open: no grade to offer. */
export const NO_GRADES: SchemeGrades = { source: [], intelligence: [], handling: [] };

/** ADR-143 decision 11 and Amendment 6: the grades an opened board offers (`grading_grades`), the
 * deployment's scheme's as the Conduit checks them. The Glass keeps no list of its own: the
 * Conduit's (`GRADING_PARTS`, or the scheme file's) is the one. */
export function offerGrades(grades: ({ scheme: string } & SchemeGrades) | null | undefined): void {
  if (grades) offered[grades.scheme] = { source: grades.source, intelligence: grades.intelligence, handling: grades.handling };
}

/** A scheme's grades, as an opened board offered them. */
export function gradesOf(scheme: string): SchemeGrades | undefined {
  return offered[scheme];
}

const NAME_KEYS = ["name", "family_name", "value_normalised", "account_number", "title"] as const;

/** What the board calls an item: a drawn one by the analyst's own label, a loaded one by its name. */
export function itemLabel(node: BoardNode): string {
  const drawn = node.provenance.drawn;
  if (drawn) return drawn.label;
  const properties = (node.properties ?? {}) as Record<string, unknown>;
  for (const key of NAME_KEYS) {
    const value = properties[key];
    if (typeof value === "string" && value.trim()) {
      const given = properties.given_names;
      if (key === "family_name" && typeof given === "string" && given.trim()) return `${given} ${value}`;
      return value;
    }
  }
  return `Unnamed ${node.type}`;
}

export function linkLabel(edge: BoardEdge): string {
  if (edge.provenance.drawn) return edge.provenance.drawn.label;
  if (edge.type === "SAME_AS") return "same as";
  if (edge.type === "NOT_SAME_AS") return "not the same as";
  return edge.type.toLowerCase().replaceAll("_", " ");
}

export function isDrawn(element: { provenance: { drawn?: unknown } }): boolean {
  return Boolean(element.provenance.drawn);
}

export function clamp(value: number): number {
  return Math.min(0.95, Math.max(0.05, value));
}

/** Where each item sits: its kept place, else the next free place on a grid, in reading order. */
export function placed(opened: BoardOpened): Record<string, Position> {
  const layout = (opened.layout ?? {}) as Record<string, Position>;
  const out: Record<string, Position> = {};
  let free = 0;
  for (const node of opened.nodes) {
    const kept = layout[node.id];
    if (kept && typeof kept.x === "number" && typeof kept.y === "number") {
      out[node.id] = { x: clamp(kept.x), y: clamp(kept.y) };
      continue;
    }
    const column = free % 4;
    const row = Math.floor(free / 4);
    out[node.id] = { x: clamp(0.15 + column * 0.23), y: clamp(0.15 + row * 0.2) };
    free += 1;
  }
  return out;
}

/** An arrow key's move (decision 5's "move by arrow keys"): a small step, or a large one with Shift. */
export function moved(at: Position, key: string, large: boolean): Position | null {
  const step = large ? 0.1 : 0.02;
  switch (key) {
    case "ArrowLeft":
      return { x: clamp(at.x - step), y: at.y };
    case "ArrowRight":
      return { x: clamp(at.x + step), y: at.y };
    case "ArrowUp":
      return { x: at.x, y: clamp(at.y - step) };
    case "ArrowDown":
      return { x: at.x, y: clamp(at.y + step) };
    default:
      return null;
  }
}

/** Where a new item goes: below and right of the last one, or the board's middle. */
export function nextPlace(positions: Record<string, Position>): Position {
  const all = Object.values(positions);
  if (all.length === 0) return { x: 0.5, y: 0.5 };
  const last = all[all.length - 1]!;
  return { x: clamp(last.x + 0.12 > 0.9 ? 0.15 : last.x + 0.12), y: clamp(last.x + 0.12 > 0.9 ? last.y + 0.18 : last.y) };
}
