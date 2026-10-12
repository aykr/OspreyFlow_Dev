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
  /** How many are open there (ADR-115 E6: the alert queue's count); none drawn for nothing. */
  badge?: number;
}

export function LeftRail({ items, onHelp }: { items: readonly RailItem[]; onHelp?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <nav aria-label="Workspace" className="left-rail" data-expanded={expanded ? "true" : undefined}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className="left-rail__item"
          aria-label={item.badge ? `${item.label}, ${item.badge.toLocaleString("en-GB")} open` : item.label}
          aria-pressed={item.pressed === undefined ? undefined : item.pressed}
          title={expanded ? undefined : item.label}
          onClick={item.onSelect}
        >
          <Icon name={item.icon} />
          {item.badge ? (
            <span className="value left-rail__badge" aria-hidden="true">
              {item.badge > 99 ? "99+" : item.badge}
            </span>
          ) : null}
          {expanded && <span className="left-rail__name">{item.label}</span>}
        </button>
      ))}
      {onHelp && (
        // ADR-115 E6: reopens the workspace's welcome panel, as `?` does.
        <button type="button" className="left-rail__item left-rail__help" aria-label="Help" title="Help (?)" aria-keyshortcuts="?" onClick={onHelp}>
          <span aria-hidden="true" className="left-rail__glyph">?</span>
          {expanded && <span className="left-rail__name">Help</span>}
        </button>
      )}
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
