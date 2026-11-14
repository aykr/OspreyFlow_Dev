import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";

export interface RadialMenuItem {
  id: string;
  label: string;
  /** How many nodes this entry would bring in, from `/expand/preview` —
   * `08_ACCEPTANCE_SCENARIOS.md` A1's "expansion previews its cardinality
   * before running". **`null` means "not answered yet", and renders as `…`,
   * never as `0`**: before round 12c every entry was hardcoded to 0, so the
   * menu used identical text for "nothing there" and "eight there", which is
   * worse than showing no figure at all. An action whose count is unknown
   * stays selectable — a missing preview is a reason to say so, not a reason
   * to block the expansion behind it. */
  count: number | null | "unavailable" | undefined;
  onSelect: () => void;
  /** The heading this entry sits under in the list layout (ADR-078). Entries that follow one another
   * with the same heading share it; entries with none are listed flat. Never changes the order. */
  group?: string;
  /** Acts without closing the menu (ADR-078 Amendment 1: "7 types with no links" opens in place). Focus
   * stays in the menu, on the first entry. */
  keepsOpen?: boolean;
}

/** `…` only while a preview is in flight; `count unavailable` when it failed; nothing at all for
 * an action that has no count (`undefined`), so a placeholder `0` is never shown. */
function countLabel(count: RadialMenuItem["count"]): string {
  if (count === undefined) return "";
  const text =
    count === null
      ? "…"
      : count === "unavailable"
        ? "count unavailable"
        : String(count);
  return ` (${text})`;
}

/** An entry's name and, when it has one, its count as a separate muted element at the right edge. */
function ItemBody({ item }: { item: RadialMenuItem }) {
  const count = countLabel(item.count);
  return (
    <>
      {item.label}
      {count === "" ? null : <span className="radial-menu__count">{count}</span>}
    </>
  );
}

export interface RadialMenuProps {
  x: number;
  y: number;
  items: RadialMenuItem[];
  onClose: () => void;
  /** `spec/02_GLASS_FRONTEND.md` §6 accessibility floor: "`\` opens the
   * radial menu as a list" — the same menu, a different arrangement, not
   * a different feature. Mouse-invoked (right-click) defaults to the
   * radial layout; keyboard-invoked (`\`) defaults to the list. */
  layout: "radial" | "list";
  /** What the menu applies to, shown at its head ("2 selected", or the item's name; ADR-078 Amendment 1), so
   * that with several nodes in view the analyst can tell which one it belongs to. */
  title?: string;
  /** ADR-078 Amendment 1: the menu never opens over the bottom bar. The page y the menu's last entry must
   * stay above (the bar's top), or null when nothing is there; the menu moves up to clear it. */
  keepAbove?: () => number | null;
}

const RADIUS = 96;

const CLEARANCE = 8;

/** Arrow keys step through the entries (wrapping), Home and End go to the ends: every entry is
 * reachable by keyboard in either layout (ADR-078 Amendment 1; the radial one is a ring, so its order
 * is the order given). */
function moveFocus(e: ReactKeyboardEvent<HTMLUListElement>) {
  const entries = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[role='menuitem']"));
  if (entries.length === 0) return;
  const at = entries.indexOf(document.activeElement as HTMLElement);
  const next =
    e.key === "ArrowDown" || e.key === "ArrowRight"
      ? (at + 1) % entries.length
      : e.key === "ArrowUp" || e.key === "ArrowLeft"
        ? (at - 1 + entries.length) % entries.length
        : e.key === "Home"
          ? 0
          : e.key === "End"
            ? entries.length - 1
            : null;
  if (next === null) return;
  e.preventDefault();
  e.stopPropagation(); // the canvas's own arrow keys move between nodes; not while its menu is open
  entries[next]?.focus();
}

export function RadialMenu({ x, y, items, onClose, layout, title, keepAbove }: RadialMenuProps) {
  const ref = useRef<HTMLUListElement>(null);
  // Where it was moved to, for the `y` it was measured at: a menu opened somewhere else starts at its own y.
  const [placed, setPlaced] = useState({ y, top: y });
  const top = placed.y === y ? placed.top : y;

  // Measured once drawn: the lowest edge of the menu or any entry (the ring's entries sit outside the
  // list's own box) is kept above `keepAbove`'s line, moving the whole menu up by what it overlaps.
  useLayoutEffect(() => {
    const line = keepAbove?.();
    const menu = ref.current;
    if (line == null || !menu) return;
    const boxes = [menu, ...Array.from(menu.querySelectorAll<HTMLElement>("[role='menuitem']"))];
    const bottom = Math.max(...boxes.map((el) => el.getBoundingClientRect().bottom));
    const over = bottom + CLEARANCE - line;
    if (over > 0) setPlaced({ y, top: Math.max(CLEARANCE, top - over) });
    // Measured on open and when the entries change (a count arriving, a fold opening).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length, y]);

  // An entry that had focus can leave the menu as its entries change (a fold, an answer arriving): focus
  // then stays in the menu, on its first entry, so the arrow keys keep working.
  const entryIds = items.map((i) => i.id).join("\n");
  useLayoutEffect(() => {
    const menu = ref.current;
    if (menu && (document.activeElement === document.body || document.activeElement === null))
      menu.querySelector<HTMLElement>("[role='menuitem']")?.focus();
  }, [entryIds]);

  const choose = (item: RadialMenuItem) => {
    item.onSelect();
    if (item.keepsOpen) {
      requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus());
      return;
    }
    onClose();
  };

  // **Focus the first item once, on open — not on every render.** These were one effect keyed on
  // `[onClose]` until round 12d. `onClose` is an inline arrow at the call site, so its identity
  // changes on every parent render, so the effect re-ran and moved focus back to the first item
  // each time. Nothing exercised that while the menu was open, because nothing used to re-render
  // it once opened — until `/expand/preview` started filling the cardinalities in (round 12c),
  // at which point a keyboard user arrow-ing down the list was silently thrown back to the top
  // mid-navigation, and two existing keyboard cases went red.
  //
  // The empty dependency array is the point: "on mount" is the real intent, and expressing it as
  // `[onClose]` only ever worked because the menu never re-rendered.
  // A layout effect, so Escape is heard from the moment it can be seen (as `Popover`).
  useLayoutEffect(() => {
    ref.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus();
  }, []);

  // A layout effect, so Escape is heard from the moment it can be seen (as `Popover`).
  useLayoutEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // A click anywhere outside the menu closes it, the same as every other menu on the page.
  useEffect(() => {
    const onPointerDown = (e: MouseEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [onClose]);

  const heading = title ? (
    <li
      role="none"
      className="radial-menu__title"
      style={{
        padding: "var(--sp-4) var(--sp-8)",
        color: "var(--text-secondary)",
        borderBottom: "1px solid var(--border-subtle)",
        // ADR-097 Amendment 3: a heading is in the page's own face; mono is for values.
        fontFamily: "var(--ui)",
        whiteSpace: "nowrap",
      }}
    >
      {title}
    </li>
  ) : null;

  if (layout === "list") {
    const entry = (item: RadialMenuItem) => (
      <li key={item.id} role="none">
        <button
          role="menuitem"
          type="button"
          className="radial-menu__item"
          style={{
            background: "none",
            border: "none",
            width: "100%",
            textAlign: "left",
          }}
          onClick={() => choose(item)}
        >
          <ItemBody item={item} />
        </button>
      </li>
    );
    // Entries under one heading are drawn together, in the order given, so a keyboard user reaches
    // them in the same order as before: the headings are not focusable and not read as entries.
    const runs: { group: string | undefined; items: RadialMenuItem[] }[] = [];
    for (const item of items) {
      const last = runs[runs.length - 1];
      if (last && last.group === item.group) last.items.push(item);
      else runs.push({ group: item.group, items: [item] });
    }
    return (
      <ul
        className="radial-menu__list"
        role="menu"
        aria-label={title}
        ref={ref}
        onKeyDown={moveFocus}
        style={{ position: "fixed", left: x, top }}
      >
        {heading}
        {runs.map((run, i) =>
          run.group === undefined ? (
            run.items.map(entry)
          ) : (
            <li key={`${run.group}-${i}`} role="none" className="radial-menu__group">
              <span className="radial-menu__group-title" aria-hidden="true">
                {run.group}
              </span>
              <ul role="group" aria-label={run.group} className="radial-menu__group-items">
                {run.items.map(entry)}
              </ul>
            </li>
          ),
        )}
      </ul>
    );
  }

  return (
    <ul
      className="radial-menu"
      role="menu"
      aria-label={title}
      ref={ref}
      onKeyDown={moveFocus}
      style={{
        position: "fixed",
        left: x,
        top,
        listStyle: "none",
        margin: 0,
        padding: 0,
      }}
    >
      {heading}
      {items.map((item, i) => {
        const angle = (i / items.length) * 2 * Math.PI - Math.PI / 2;
        const itemX = Math.cos(angle) * RADIUS;
        const itemY = Math.sin(angle) * RADIUS;
        return (
          <li
            key={item.id}
            role="none"
            style={{
              position: "absolute",
              transform: `translate(${itemX}px, ${itemY}px)`,
            }}
          >
            <button
              role="menuitem"
              type="button"
              className="radial-menu__item"
              onClick={() => choose(item)}
            >
              <ItemBody item={item} />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
