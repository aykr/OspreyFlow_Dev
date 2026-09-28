import type { ReactNode } from "react";

export interface PanelProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

/** Docked, always: hairline border, no shadow — `spec/02_GLASS_FRONTEND.md`
 * §8: "Docked panels get a hairline and no shadow; overlays get a shadow
 * and no hairline. Never both." Use `Drawer`/`Popover` for overlays. */
export function Panel({ title, children, className }: PanelProps) {
  return (
    <section className={["panel", className].filter(Boolean).join(" ")}>
      {title && <h2 className="panel__title">{title}</h2>}
      <div className="panel__body">{children}</div>
    </section>
  );
}
