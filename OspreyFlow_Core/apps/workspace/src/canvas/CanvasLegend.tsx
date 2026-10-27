// The legend (ADR-097 step 2, design review item 10): each type now in view, drawn as the canvas
// draws it, with how many there are, most first. It folds to its title, and the list stays in the
// page while folded.
//
// It floats (the owner, 14 October 2026: "the legend is hiding the button behind, can the legend
// panel be a floating panel"): it docks at the canvas's top right, just below the toolbar, and its
// grip moves it — dragged, or with the grip focused, the arrows by 16px, Shift with them by 64px,
// Home back to its dock (as a panel's sash moves). It never rises above its dock, so it cannot cover
// the toolbar, and stays inside the canvas. Where it was put is this browser's, like the grid.
//
// Under the types, the links in view (ADR-117): each link type in its colour with how many, and a
// box to leave it out of the view or bring it back — the "links to include" a prison analyst filters
// a network by. Leaving a type out hides its links in this view only, like hiding one link.
//
// Under the links, the icons chosen by a property's value (ADR-128 Decision 4): each drawing in use in
// the view, what it means and how many nodes carry it, so an icon is never a guess.
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { activePalette } from "../color/palette";
import { TypeChip } from "../inspector/TypeChip";
import type { EntityVisual } from "../ontology/schema";
import { describeValueIcon, glyphImageUri } from "./valueIcons";

export interface LegendType {
  type: string;
  count: number;
  visual?: EntityVisual;
}

/** One icon chosen by a property's value that is drawn in the view now (ADR-128 Decision 4). */
export interface LegendValueIcon {
  type: string;
  property: string;
  value: string;
  glyph: string;
  count: number;
}

export interface LegendLink {
  type: string;
  label: string;
  count: number;
  /** The type's declared colour, one of the nine data channels, or null for the ordinary line. */
  colour: string | null;
  shown: boolean;
}

// The nine data channels (`design/tokens.css`); any other name draws the ordinary line colour, so
// no colour outside the tokens reaches the legend.
const CHANNELS: ReadonlySet<string> = new Set([
  "ochre", "rose", "plum", "violet", "indigo", "azure", "cyan", "jade", "moss",
]);

function swatch(colour: string | null): string {
  return colour !== null && CHANNELS.has(colour) ? `var(--ch-${colour})` : "var(--border-strong)";
}

interface Offset {
  x: number;
  y: number;
}

const OFFSET_KEY = "ospreyflow.canvas-legend-offset";
const STEP = 16;
const BIG_STEP = 64;
const DOCKED: Offset = { x: 0, y: 0 };

function remembered(): Offset {
  try {
    const held = JSON.parse(localStorage.getItem(OFFSET_KEY) ?? "null") as Offset | null;
    if (held && Number.isFinite(held.x) && Number.isFinite(held.y)) return { x: held.x, y: Math.max(0, held.y) };
  } catch {
    // Private window, blocked storage or a stale value: it docks.
  }
  return DOCKED;
}

function remember(offset: Offset) {
  try {
    if (offset.x === 0 && offset.y === 0) localStorage.removeItem(OFFSET_KEY);
    else localStorage.setItem(OFFSET_KEY, JSON.stringify(offset));
  } catch {
    // The place lasts for this page.
  }
}

export function CanvasLegend({
  types,
  links = [],
  valueIcons = [],
  onToggleLink,
}: {
  types: readonly LegendType[];
  links?: readonly LegendLink[];
  valueIcons?: readonly LegendValueIcon[];
  onToggleLink?: (type: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const [offset, setOffset] = useState<Offset>(remembered);
  const legendRef = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{ x: number; y: number; from: Offset; at: Offset } | null>(null);

  // Below its dock never, and inside the canvas when the canvas can be measured.
  const within = (wanted: Offset): Offset => {
    const next = { x: wanted.x, y: Math.max(0, wanted.y) };
    const legend = legendRef.current;
    const canvas = legend?.parentElement?.offsetParent as HTMLElement | null | undefined;
    if (!legend || !canvas) return next;
    const area = canvas.getBoundingClientRect();
    const box = legend.getBoundingClientRect();
    if (area.width === 0 || box.width === 0) return next;
    const dockLeft = box.left - offset.x;
    const dockTop = box.top - offset.y;
    next.x = Math.min(Math.max(next.x, area.left + 4 - dockLeft), area.right - 4 - box.width - dockLeft);
    next.y = Math.min(next.y, Math.max(0, area.bottom - 4 - box.height - dockTop));
    return next;
  };

  const place = (wanted: Offset) => {
    const next = within(wanted);
    setOffset(next);
    remember(next);
  };

  const onGripKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step = event.shiftKey ? BIG_STEP : STEP;
    const moves: Record<string, Offset> = {
      ArrowLeft: { x: offset.x - step, y: offset.y },
      ArrowRight: { x: offset.x + step, y: offset.y },
      ArrowUp: { x: offset.x, y: offset.y - step },
      ArrowDown: { x: offset.x, y: offset.y + step },
      Home: DOCKED,
    };
    const next = moves[event.key];
    if (!next) return;
    event.preventDefault();
    place(next);
  };

  const onPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    // Only the primary button starts a drag; a test double with no button counts as primary.
    if (event.button !== undefined && event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, from: offset, at: offset };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  };
  const onPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const start = drag.current;
    if (!start) return;
    start.at = within({ x: start.from.x + event.clientX - start.x, y: start.from.y + event.clientY - start.y });
    setOffset(start.at);
  };
  const onPointerUp = () => {
    const start = drag.current;
    if (!start) return;
    drag.current = null;
    remember(start.at);
  };

  if (types.length === 0) return null;
  const sorted = [...types].sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));
  const moved = offset.x !== 0 || offset.y !== 0;
  return (
    <div
      ref={legendRef}
      className={moved ? "canvas-legend canvas-legend--moved" : "canvas-legend"}
      style={moved ? { transform: `translate(${offset.x}px, ${offset.y}px)` } : undefined}
    >
      <div className="canvas-legend__head">
        <button type="button" className="canvas-legend__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          Legend
        </button>
        <button
          type="button"
          className="canvas-legend__grip"
          aria-label="Move legend"
          title="Move legend: drag, or arrow keys (Shift for further, Home to put it back)"
          aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown Home"
          onKeyDown={onGripKey}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={() => (drag.current = null)}
        >
          ⠿
        </button>
      </div>
      <ul aria-label="Types in view" className="canvas-legend__list" hidden={!open}>
        {sorted.map((t) => (
          <li key={t.type}>
            <TypeChip type={t.type} visual={t.visual} />
            <span className="value">{t.count.toLocaleString("en-GB")}</span>
          </li>
        ))}
      </ul>
      {valueIcons.length > 0 && (
        <ul aria-label="Icons by value" className="canvas-legend__list canvas-legend__links" hidden={!open}>
          {[...valueIcons]
            .sort((a, b) => b.count - a.count || a.glyph.localeCompare(b.glyph) || a.type.localeCompare(b.type))
            .map((v) => (
              <li key={`${v.type}:${v.property}:${v.value}`}>
                <span className="canvas-legend__meaning">
                  <img alt="" width={14} height={14} src={glyphImageUri(v.glyph, activePalette().textPrimary) ?? undefined} />
                  {describeValueIcon(v.type, v.property, v.value, v.glyph)}
                </span>
                <span className="value">{v.count.toLocaleString("en-GB")}</span>
              </li>
            ))}
        </ul>
      )}
      {links.length > 0 && (
        <ul aria-label="Links in view" className="canvas-legend__list canvas-legend__links" hidden={!open}>
          {[...links]
            .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
            .map((l) => (
              <li key={l.type}>
                <label className="canvas-legend__link">
                  <input
                    type="checkbox"
                    checked={l.shown}
                    disabled={onToggleLink === undefined}
                    onChange={() => onToggleLink?.(l.type)}
                  />
                  <span className="canvas-legend__swatch" style={{ background: swatch(l.colour) }} aria-hidden="true" />
                  {l.label}
                </label>
                <span className="value">{l.count.toLocaleString("en-GB")}</span>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
