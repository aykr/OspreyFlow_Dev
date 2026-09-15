import type { CSSProperties, ReactNode } from "react";

export interface PopoverProps {
  x: number;
  y: number;
  children: ReactNode;
}

/** A positioned overlay anchored at a page coordinate — the base every
 * DOM-anchored overlay in the Glass builds on (edge inspection, hover
 * cards): `docs/02_GLASS_FRONTEND.md` §1.1: "Labels, hover cards and
 * context menus are DOM overlays positioned from Sigma's camera... The
 * rich parts stay in HTML where they are easy." */
export function Popover({ x, y, children }: PopoverProps) {
  const style: CSSProperties = { position: "fixed", left: x, top: y, zIndex: 30 };
  return (
    <div className="popover" style={style} role="dialog">
      {children}
    </div>
  );
}
