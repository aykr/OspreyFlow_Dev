// The top bar (ADR-097 step 1, design review item 1): 40px, one row. The mark, the place switcher
// (ADR-145 decision 1; inside the GOV.UK header under that brand), search, the one view switch (Graph,
// Map, Drawing board and Reports, with Matrix, Figures, Ownership and Connection strength under More views,
// ADR-145 Amendment 15), then what acts on the whole case, and the account at the right. The case is in the
// context banner under the bar (ADR-145 decision 2), with Cases reached from its switcher and Views in this
// case; the left rail only opens panels; what belongs to one view is on that view's own toolbar.
//
// When the bar runs out of room on one line (a narrower window, a wider font), what is used least folds away in
// `BAR_FOLD_ORDER`'s order (the owner's ruling of 14 November 2026, spec 02 §3): *Build a report* and the views into
// More views, the places into one menu. The bar stays one line high; only when everything that folds has folded do
// whole items wrap, and the account and its clearance never leave the screen (ADR-065 decision 6).
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";

import { DropdownPanel } from "../design/primitives/DropdownPanel";
import { ThemeToggle } from "../theme/ThemeToggle";
import { currentBrand } from "../brand/brand";
import { BrandMark } from "./BrandMark";
import { BAR_FOLD_ORDER } from "./railLayout";
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
  /** The place switcher (`PlaceSwitcher`); given as a function, it is told when the bar has folded it into one menu. */
  places?: ReactNode | ((folded: boolean) => ReactNode);
  /** The case switcher, where a surface keeps it in the bar rather than the banner. */
  caseSwitcher?: ReactNode;
  search?: ReactNode;
  views?: readonly TopBarView[];
  /** One click away under *More views* (ADR-145 Amendments 2 and 15: Matrix, Figures, Ownership, Connection strength). */
  moreViews?: readonly TopBarView[];
  /** The address of the owner's *Build a report* (ADR-145 Amendment 15), drawn beside the view switch's last entry,
   * before *More views*: a link out of the Glass, so outside the switch's group. The first to fold into More views. */
  buildAReport?: string;
  /** What acts on the whole case, such as Export. */
  actions?: ReactNode;
  account: ReactNode;
  /** The mark as the way back to Start (ADR-114 Amendment 5 point 9). */
  onStart?: () => void;
}

/** Whether any item of the bar sits on a second line: one whose top is at or below the bottom of the shortest item
 * (items are centred in the row, so every item of the first row starts above that). Items drawn with no size (none in
 * jsdom) are not counted. */
export function barWraps(bar: HTMLElement): boolean {
  const boxes = [...bar.children].map((child) => child.getBoundingClientRect()).filter((box) => box.width > 0 && box.height > 0);
  if (boxes.length < 2) return false;
  const firstRowBottom = Math.min(...boxes.map((box) => box.bottom));
  return boxes.some((box) => box.top >= firstRowBottom - 0.5);
}

/** What can fold on this bar, in `BAR_FOLD_ORDER`'s order: a view the order does not name folds just before Graph. */
export function foldSteps(views: readonly { id: string }[], has: { places: boolean; buildAReport: boolean }): string[] {
  const named: readonly string[] = BAR_FOLD_ORDER;
  const unnamed = views.map((view) => view.id).filter((id) => !named.includes(id)).reverse();
  return BAR_FOLD_ORDER.flatMap((step) => (step === "graph" ? [...unnamed, step] : [step])).filter((step) =>
    step === "places" ? has.places : step === "build-a-report" ? has.buildAReport : views.some((view) => view.id === step),
  );
}

export function TopBar({ app, places, caseSwitcher, search, views = [], moreViews = [], buildAReport, actions, account, onStart }: TopBarProps) {
  const bar = useRef<HTMLElement>(null);
  const steps = foldSteps(views, { places: places !== undefined && places !== null, buildAReport: buildAReport !== undefined });
  // What is folded: the first `fold` of `steps`. It starts again from none whenever what could fold, or the view open,
  // changes (the More views button names a folded view that is open, so its width changes with it).
  const key = `${steps.join(",")}|${views.find((view) => view.pressed)?.id ?? ""}|${moreViews.find((view) => view.pressed)?.id ?? ""}`;
  // `pass` counts each start from none folded, so a start when none is folded already still measures again.
  const [fold, setFold] = useState({ key, count: 0, pass: 0 });
  if (fold.key !== key) setFold({ key, count: 0, pass: fold.pass + 1 });
  const count = fold.key === key ? fold.count : 0;
  const folded = new Set(steps.slice(0, count));
  const stepCount = useRef(steps.length);
  stepCount.current = steps.length;
  // Whether whole items wrap even so, with all that folds folded: only then do the two lines get room above and below.
  const [wrapped, setWrapped] = useState(false);

  // After each change of what is folded, before the screen is painted: one more folds while an item sits on a second
  // line. (An item that grows later changes the bar's height, which the observer below sees.)
  useLayoutEffect(() => {
    if (!bar.current) return;
    const wraps = barWraps(bar.current);
    if (wraps && count < steps.length) setFold((current) => ({ ...current, count: count + 1 }));
    else setWrapped(wraps);
  }, [count, key, steps.length, fold.pass]);
  // A change of the bar's width starts again from none folded (a wider window unfolds); a change of its height alone
  // (a font arriving, an item growing) folds one more if it now wraps.
  useLayoutEffect(() => {
    const element = bar.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    let width = element.clientWidth;
    const observer = new ResizeObserver(() => {
      const now = element.clientWidth;
      if (now !== width) {
        width = now;
        flushSync(() => setFold((current) => ({ ...current, count: 0, pass: current.pass + 1 })));
      } else if (barWraps(element)) {
        flushSync(() => {
          setFold((current) => ({ ...current, count: Math.min(current.count + 1, stepCount.current) }));
        });
      } else {
        flushSync(() => setWrapped(false));
      }
    });
    observer.observe(element);
    // A web font arriving can make the items narrower as well as wider: measure again from none folded.
    const fonts = typeof document !== "undefined" ? document.fonts : undefined;
    const again = () => flushSync(() => setFold((current) => ({ ...current, count: 0, pass: current.pass + 1 })));
    let live = true;
    fonts?.addEventListener?.("loadingdone", again);
    void fonts?.ready?.then(() => live && again());
    return () => {
      live = false;
      observer.disconnect();
      fonts?.removeEventListener?.("loadingdone", again);
    };
  }, []);

  const shownViews = views.filter((view) => !folded.has(view.id));
  // Folded views lead More views, in the switch's own order, then More views' own.
  const menuViews = [...views.filter((view) => folded.has(view.id)), ...moreViews];
  const linkFolded = buildAReport !== undefined && folded.has("build-a-report");
  const moreOpen = menuViews.find((view) => view.pressed);
  return (
    <header className={wrapped ? "app-header top-bar top-bar--wrapped" : "app-header top-bar"} data-app={app} data-folded={count > 0 ? steps.slice(0, count).join(" ") : undefined} ref={bar}>
      {onStart ? (
        <button type="button" className="brand-mark-button" aria-label="Osprey, go to Home" onClick={onStart}>
          <BrandMark />
        </button>
      ) : (
        <BrandMark />
      )}
      {typeof places === "function" ? places(folded.has("places")) : places}
      {caseSwitcher}
      {search && <div className="top-bar__search">{search}</div>}
      {shownViews.length > 0 && (
        <div role="group" aria-label="View" className="segmented">
          {shownViews.map((view) => (
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
      {buildAReport !== undefined && !linkFolded && <BuildAReportLink href={buildAReport} />}
      {(menuViews.length > 0 || linkFolded) && (
        // ADR-145 Amendment 2: the views used less, one click away; the one open names the button.
        <DropdownPanel
          label={moreOpen ? moreOpen.label : "More views"}
          panelLabel="More views"
          buttonClassName={moreOpen ? "menu-button--pressed" : undefined}
        >
          {(close) => (
            <>
              {menuViews.map((view) => (
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
              ))}
              {linkFolded && (
                <a href={buildAReport} target="_blank" rel="noopener noreferrer" className="menu-panel__item" onClick={close}>
                  Build a report (opens in new tab)
                </a>
              )}
            </>
          )}
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
 * said so in the link's own words. Drawn beside the view switch (`buildAReport`) only for a holder of manage_dashboards
 * where Superset is deployed; the caller decides that. */
export function BuildAReportLink({ href }: { href: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={currentBrand() === "govuk" ? "govuk-link top-bar__out" : "top-bar__out"}>
      Build a report (opens in new tab)
    </a>
  );
}
