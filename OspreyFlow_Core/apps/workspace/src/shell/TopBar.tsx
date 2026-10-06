// The top bar (ADR-097 step 1, design review item 1): 40px, one row. The mark, the case, search, the
// view switch, then what acts on the whole case, and the account at the right. The places the
// analyst goes to (cases, watches, history, proposed types, the Ingest Studio) are on the left rail,
// and what belongs to one view is on that view's own toolbar.
import type { ReactNode } from "react";

import { BrandMark } from "./BrandMark";

export interface TopBarView {
  id: string;
  label: string;
  pressed: boolean;
  onSelect: () => void;
}

export interface TopBarProps {
  /** Which application is open, for the line under the bar in the Ingest Studio (ADR-065). */
  app: "glass" | "ingest";
  caseSwitcher: ReactNode;
  search?: ReactNode;
  views?: readonly TopBarView[];
  /** What acts on the whole case, such as Export. */
  actions?: ReactNode;
  account: ReactNode;
}

export function TopBar({ app, caseSwitcher, search, views = [], actions, account }: TopBarProps) {
  return (
    <header className="app-header top-bar" data-app={app}>
      <BrandMark />
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
      {actions}
      <div className="app-header__account" style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        {account}
      </div>
    </header>
  );
}
