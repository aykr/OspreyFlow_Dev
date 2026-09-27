import { useEffect, useRef } from "react";

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
  count: number | null;
  onSelect: () => void;
}

/** `…` while a preview is in flight or could not be fetched. */
function countLabel(count: number | null): string {
  return count === null ? "…" : String(count);
}

export interface RadialMenuProps {
  x: number;
  y: number;
  items: RadialMenuItem[];
  onClose: () => void;
  /** `docs/02_GLASS_FRONTEND.md` §6 accessibility floor: "`\` opens the
   * radial menu as a list" — the same menu, a different arrangement, not
   * a different feature. Mouse-invoked (right-click) defaults to the
   * radial layout; keyboard-invoked (`\`) defaults to the list. */
  layout: "radial" | "list";
}

const RADIUS = 96;

export function RadialMenu({ x, y, items, onClose, layout }: RadialMenuProps) {
  const ref = useRef<HTMLUListElement>(null);

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (layout === "list") {
    return (
      <ul
        className="radial-menu__list"
        role="menu"
        ref={ref}
        style={{ position: "fixed", left: x, top: y }}
      >
        {items.map((item) => (
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
              onClick={() => {
                item.onSelect();
                onClose();
              }}
            >
              {item.label} ({countLabel(item.count)})
            </button>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul
      className="radial-menu"
      role="menu"
      ref={ref}
      style={{
        position: "fixed",
        left: x,
        top: y,
        listStyle: "none",
        margin: 0,
        padding: 0,
      }}
    >
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
              onClick={() => {
                item.onSelect();
                onClose();
              }}
            >
              {item.label} ({countLabel(item.count)})
            </button>
          </li>
        );
      })}
    </ul>
  );
}
