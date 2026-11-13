// The top bar (ADR-097 step 1, design review item 1): 40px, one row. The mark, the place switcher
// (ADR-145 decision 1; inside the GOV.UK header under that brand), search, the view switch (Graph and
// Map, with Matrix and Reports under More views, ADR-145 Amendment 2), then what acts on the whole
// case, and the account at the right. The case and Monitoring are in the context banner under the bar
// (ADR-145 decision 2); Cases and Explore are on the left rail, the rest under its ⋯ More; what belongs
// to one view is on that view's own toolbar.
import { DropdownPanel } from "../design/primitives/DropdownPanel";
import { ThemeToggle } from "../theme/ThemeToggle";
import type { ReactNode } from "react";

import { currentBrand } from "../brand/brand";
import { BrandMark } from "./BrandMark";
import "./chrome.css";

export interface TopBarView {
  id: string;
  label: string;
  pressed: boolean;
  onSelect: () => void;
}

export interface TopBarProps {
  /** Which application is open, for the line under the bar in the Ingest Studio (ADR-065). */
  app: "glass" | "ingest" | "rules";
  /** The place switcher (`PlaceSwitcher`). */
  places?: ReactNode;
  /** The case switcher, where a surface keeps it in the bar rather than the banner. */
  caseSwitcher?: ReactNode;
  search?: ReactNode;
  views?: readonly TopBarView[];
  /** One click away under *More views* (ADR-145 Amendments 2 and 15: Matrix, Figures, Ownership, Connection strength). */
  moreViews?: readonly TopBarView[];
  /** Beside the view switch's last entry, before *More views*: the owner's *Build a report* (ADR-145 Amendment 15),
   * a link out of the Glass, so outside the switch's group. */
  besideViews?: ReactNode;
  /** What acts on the whole case, such as Export. */
  actions?: ReactNode;
  account: ReactNode;
  /** The mark as the way back to Start (ADR-114 Amendment 5 point 9). */
  onStart?: () => void;
}

export function TopBar({ app, places, caseSwitcher, search, views = [], moreViews = [], besideViews, actions, account, onStart }: TopBarProps) {
  const moreOpen = moreViews.find((view) => view.pressed);
  return (
    <header className="app-header top-bar" data-app={app}>
      {onStart ? (
        <button type="button" className="brand-mark-button" aria-label="Osprey, go to Home" onClick={onStart}>
          <BrandMark />
        </button>
      ) : (
        <BrandMark />
      )}
      {places}
      {caseSwitcher}
      {search && <div className="top-bar__search">{search}</div>}
      {views.length > 0 && (
        <div role="group" aria-label="View" className="segmented">
          {views.map((view) => (
            <button
              key={view.id}
              type="button"
              className="segmented__item"
              aria-pressed={view.pressed}
              onClick={view.onSelect}
            >
              {view.label}
            </button>
          ))}
        </div>
      )}
      {besideViews}
      {moreViews.length > 0 && (
        // ADR-145 Amendment 2: the views used less, one click away; the one open names the button.
        <DropdownPanel
          label={moreOpen ? moreOpen.label : "More views"}
          panelLabel="More views"
          buttonClassName={moreOpen ? "menu-button--pressed" : undefined}
        >
          {(close) =>
            moreViews.map((view) => (
              <button
                key={view.id}
                type="button"
                className="menu-panel__item"
                aria-current={view.pressed ? "page" : undefined}
                onClick={() => {
                  close();
                  view.onSelect();
                }}
              >
                {view.label}
              </button>
            ))
          }
        </DropdownPanel>
      )}
      {actions}
      <div className="app-header__account" style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        {/* ADR-115 Amendment 1: the theme, an icon of its own, just before the account. */}
        <ThemeToggle variant="icon" />
        {account}
      </div>
    </header>
  );
}

/** The owner's *Build a report* (ruling of 13 November 2026, Q2; ADR-145 Amendment 15): Superset's address in a new tab,
 * said so in the link's own words. Drawn beside the view switch (`besideViews`) only for a holder of manage_dashboards
 * where Superset is deployed; the caller decides that. */
export function BuildAReportLink({ href }: { href: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={currentBrand() === "govuk" ? "govuk-link top-bar__out" : "top-bar__out"}>
      Build a report (opens in new tab)
    </a>
  );
}
