// The left rail (ADR-097 step 1, design review item 1): 44px of icons, each named for assistive
// technology and on hover, and expandable to show the names. ADR-145 Amendment 15 (the owner's navigation
// decision of 13 November 2026): the rail only opens panels beside the view (Explore, Ask & Chat, History),
// then Help and Show names. Its ⋯ *Explore Details* menu (Amendment 12) is drawn only when given entries,
// and since Amendment 15 it is given none (`railLayout.ts`'s EXPLORE_DETAILS).
// Monitoring left the Glass for Rules and Monitoring, a place of its own (ADR-146 decision 2).
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
  /** For an item that opens a panel over the place (Cases, Explore, Ask & Chat, History): whether it is
   * open. Such an item is never `pressed`: the rail marks the place alone, one place, one marker
   * (ADR-145 Amendment 14 decision 3); the panel's state is `aria-expanded`. */
  expanded?: boolean;
}

/** The rail's ⋯ *Explore Details*: a menu of the destinations not on the rail itself. It closes on Escape
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
  // ADR-145 Amendment 12: named Explore Details, and, while one of its places is open, which
  // ("Explore Details, History open"); the destination open is marked inside the menu too.
  const name = "Explore Details";
  // ADR-145 Amendment 14 decision 3: the place first; a panel (History's drawer) only when no place of its own is open.
  const current = items.find((item) => item.pressed) ?? items.find((item) => item.expanded);
  const label = current ? `${name}, ${current.label} open` : name;
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
        // ADR-145 Amendment 14 decision 3: when the place open is one of its own (Ownership, Connection strength),
        // the trigger carries the rail's one marker, drawn as a pressed item's; its name says which. Not
        // `aria-pressed`: it is a menu's button (`aria-expanded`), and its name already says the place.
        data-current={current?.pressed ? "true" : undefined}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title={expanded ? undefined : label}
        onClick={() => setOpen((was) => !was)}
      >
        <span aria-hidden="true" className="left-rail__glyph">⋯</span>
        {expanded && <span className="left-rail__name">{name}</span>}
      </button>
      {open && (
        <div id={panelId} role="group" aria-label={name} className="menu-panel left-rail__more-panel">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className="menu-panel__item"
              aria-current={item === current ? "page" : undefined}
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
  /** One click away under ⋯ *Explore Details* (ADR-145 Amendment 12); none, no menu. */
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
          aria-pressed={item.expanded !== undefined || item.pressed === undefined ? undefined : item.pressed}
          aria-expanded={item.expanded}
          aria-haspopup={item.expanded === undefined ? undefined : "dialog"}
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
