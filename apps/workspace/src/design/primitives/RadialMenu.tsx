import { useEffect, useRef } from "react";

export interface RadialMenuItem {
  id: string;
  label: string;
  count: number;
  onSelect: () => void;
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
      <ul className="radial-menu__list" role="menu" ref={ref} style={{ position: "fixed", left: x, top: y }}>
        {items.map((item) => (
          <li key={item.id} role="none">
            <button
              role="menuitem"
              type="button"
              className="radial-menu__item"
              style={{ background: "none", border: "none", width: "100%", textAlign: "left" }}
              onClick={() => {
                item.onSelect();
                onClose();
              }}
            >
              {item.label} ({item.count})
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
      style={{ position: "fixed", left: x, top: y, listStyle: "none", margin: 0, padding: 0 }}
    >
      {items.map((item, i) => {
        const angle = (i / items.length) * 2 * Math.PI - Math.PI / 2;
        const itemX = Math.cos(angle) * RADIUS;
        const itemY = Math.sin(angle) * RADIUS;
        return (
          <li
            key={item.id}
            role="none"
            style={{ position: "absolute", transform: `translate(${itemX}px, ${itemY}px)` }}
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
              {item.label} ({item.count})
            </button>
          </li>
        );
      })}
    </ul>
  );
}
