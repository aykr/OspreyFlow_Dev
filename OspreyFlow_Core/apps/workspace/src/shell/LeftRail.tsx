// The left rail (ADR-097 step 1, design review item 1): 44px of icons, each named for assistive
// technology and on hover, and expandable to show the names. The places the analyst goes to rather
// than works in. ADR-145 Amendment 2 (variant B): the rail keeps the ones used most (Cases, Explore)
// and the rest are one click away under its ⋯ *More*; Monitoring is the banner's section.
import { useEffect, useId, useRef, useState } from "react";

import { Icon, type ShellIcon } from "./icons";
import "./chrome.css";

export interface RailItem {
  id: string;
  label: string;
  icon: ShellIcon;
  onSelect: () => void;
  /** This place is the one open now. */
  pressed?: boolean;
}

/** The rail's ⋯ *More*: a menu of the destinations not on the rail itself. It closes on Escape
 * (focus back on ⋯), on a choice, on a click outside, and when focus leaves it, as `DropdownPanel`
 * does, so it never traps a keyboard user. */
function RailMore({ items, expanded }: { items: readonly RailItem[]; expanded: boolean }) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as globalThis.Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);
  // One name and one role, whatever is open: the destination open is marked inside the menu.
  const label = "More";
  return (
    <div
      ref={wrapper}
      className="left-rail__more"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          trigger.current?.focus();
        }
      }}
      onBlur={(event) => {
        const next = event.relatedTarget as globalThis.Node | null;
        if (open && next && wrapper.current && !wrapper.current.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        className="left-rail__item"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title={expanded ? undefined : label}
        onClick={() => setOpen((was) => !was)}
      >
        <span aria-hidden="true" className="left-rail__glyph">⋯</span>
        {expanded && <span className="left-rail__name">More</span>}
      </button>
      {open && (
        <div id={panelId} role="group" aria-label="More" className="menu-panel left-rail__more-panel">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className="menu-panel__item"
              aria-current={item.pressed ? "page" : undefined}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function LeftRail({
  items,
  more = [],
  onHelp,
}: {
  items: readonly RailItem[];
  /** One click away under ⋯ *More* (ADR-145 Amendment 2); none, no *More*. */
  more?: readonly RailItem[];
  onHelp?: () => void;
}) {
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
      {more.length > 0 && <RailMore items={more} expanded={expanded} />}
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
