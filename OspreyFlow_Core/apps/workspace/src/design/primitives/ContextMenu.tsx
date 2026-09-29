import { useEffect, useRef } from "react";

export interface ContextMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
}

export interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

export function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLUListElement>(null);

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onClickAway = () => onClose();
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("click", onClickAway);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("click", onClickAway);
    };
  }, [onClose]);

  return (
    <ul
      className="context-menu"
      role="menu"
      ref={ref}
      style={{ position: "fixed", left: x, top: y, zIndex: 40 }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item) => (
        <li key={item.id} role="none">
          <button
            role="menuitem"
            type="button"
            className="context-menu__item"
            style={{ background: "none", border: "none", width: "100%", textAlign: "left" }}
            onClick={() => {
              item.onSelect();
              onClose();
            }}
          >
            {item.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
