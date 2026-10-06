// The left rail (ADR-097 step 1, design review item 1): 44px of icons, each named for assistive
// technology and on hover, and expandable to show the names. The places the analyst goes to rather
// than works in: the cases and their branches, watches, history, proposed types, the Ingest Studio.
import { useState } from "react";

import { Icon, type ShellIcon } from "./icons";

export interface RailItem {
  id: string;
  label: string;
  icon: ShellIcon;
  onSelect: () => void;
  /** This place is the one open now. */
  pressed?: boolean;
}

export function LeftRail({ items }: { items: readonly RailItem[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <nav aria-label="Workspace" className="left-rail" data-expanded={expanded ? "true" : undefined}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className="left-rail__item"
          aria-label={item.label}
          aria-pressed={item.pressed === undefined ? undefined : item.pressed}
          title={expanded ? undefined : item.label}
          onClick={item.onSelect}
        >
          <Icon name={item.icon} />
          {expanded && <span className="left-rail__name">{item.label}</span>}
        </button>
      ))}
      <button
        type="button"
        className="left-rail__item left-rail__toggle"
        aria-expanded={expanded}
        aria-label={expanded ? "Hide names" : "Show names"}
        title={expanded ? undefined : "Show names"}
        onClick={() => setExpanded((open) => !open)}
      >
        <Icon name="names" />
      </button>
    </nav>
  );
}
