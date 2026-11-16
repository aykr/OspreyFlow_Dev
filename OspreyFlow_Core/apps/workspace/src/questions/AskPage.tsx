// Ask & Chat in its two shapes (ADR-145 Amendment 20, v0.6.1; the owner, 16 November 2026): a drawer beside the view by
// default, as before Amendment 18, and the page of Amendment 18 when expanded. The page fills the main area over the
// view the person left, as the search results page does (`search/SearchResults.tsx`), with a back link to that view at
// its start (GOV.UK's back link under that brand); the view beneath stays as it was and is out of reach (`inert`) while
// it shows. The two shapes are one element whose chrome changes: the panel inside is never mounted again, so the
// question typed, the engine chosen and its answers go with it, and the scroll is kept on the item at its top.
import { type ReactNode, useEffect, useLayoutEffect, useRef } from "react";

import { currentBrand } from "../brand/brand";
import { useTopUnderTheChrome } from "../design/primitives/Drawer";
import type { AskForm } from "./useAskPage";
import "./askPage.css";

export interface AskPageProps {
  /** The drawer (the default, as each opening is) or the page (Expand, the results' Ask line). */
  form?: AskForm;
  /** The name of the view the person left ("Graph"), for the page's back link. */
  backLabel: string;
  /** Closes Ask & Chat entirely, focus to its opener: the page's Back, the drawer's Close, Escape inside the drawer. */
  onBack: () => void;
  /** Escape with focus outside the drawer: closes it, focus left where it is (`onBack` where not given). */
  onDismiss?: () => void;
  /** The drawer's Expand. */
  onExpand?: () => void;
  /** The page's *Show as a drawer*. */
  onCollapse?: () => void;
  /** Kept, not drawn, while a document read from an answer is open over the view. */
  hidden?: boolean;
  /** Help's keys panel, when asked for, over the page rather than beneath it. */
  beside?: ReactNode;
  /** Focus to the heading on opening; false when the page opens with words carried into the question, whose box
   * takes focus instead (the results page's *Ask a question about '…' instead*). */
  takeFocus?: boolean;
  children: ReactNode;
}

/** On the document's root while Ask & Chat's drawer shows (`askPage.css` reads it). */
export const BESIDE_DRAWER = "data-ask-drawer";

/** The item at the top of what scrolls, and how far below that top it lies. */
interface ScrollAnchor {
  element: Element;
  offset: number;
}

/** The innermost item of `within` that reaches the top of `scroller`'s visible box, descending until one starts at or
 * below it; none when nothing is scrolled. */
function anchorAtTop(scroller: HTMLElement | null, within: HTMLElement | null): ScrollAnchor | null {
  if (!scroller || !within || scroller.scrollTop === 0) return null;
  const top = scroller.getBoundingClientRect().top;
  let node: Element = within;
  let found: Element | null = null;
  for (;;) {
    const next = [...node.children].find((child) => child.getBoundingClientRect().bottom > top + 1);
    if (!next) break;
    found = next;
    if (next.getBoundingClientRect().top >= top) break;
    node = next;
  }
  return found ? { element: found, offset: found.getBoundingClientRect().top - top } : null;
}

/** Scrolls `scroller` so the anchor lies where it lay in the other shape. */
function restoreAnchor(anchor: ScrollAnchor | null, scroller: HTMLElement | null) {
  if (!anchor || !scroller || !anchor.element.isConnected) return;
  const top = scroller.getBoundingClientRect().top;
  scroller.scrollTop += anchor.element.getBoundingClientRect().top - top - anchor.offset;
}

export function AskPage({
  form = "drawer",
  backLabel,
  onBack,
  onDismiss,
  onExpand,
  onCollapse,
  hidden = false,
  beside = null,
  takeFocus = true,
  children,
}: AskPageProps) {
  const govuk = currentBrand() === "govuk";
  const drawer = form === "drawer";
  const section = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  const body = useRef<HTMLDivElement>(null);
  // What scrolls: the drawer's body under its header (as every drawer's), the whole page.
  const scroller = () => (drawer ? body.current : section.current);
  const top = useTopUnderTheChrome(drawer && !hidden);
  useEffect(() => {
    if (takeFocus) heading.current?.focus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- on opening only
  // Escape anywhere closes the drawer, as every drawer's does (`Drawer`; the orchestrator's ruling, 16 November 2026):
  // from inside it, focus goes to its opener (`onBack`); from elsewhere (the canvas), focus stays where it is
  // (`onDismiss`), as a drawer leaves it. The page has none (Amendment 18 point 4).
  const onBackRef = useRef(onBack);
  onBackRef.current = onBack;
  const onDismissRef = useRef(onDismiss ?? onBack);
  onDismissRef.current = onDismiss ?? onBack;
  useLayoutEffect(() => {
    if (!drawer || hidden) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const inside = document.activeElement instanceof Node && section.current?.contains(document.activeElement);
      (inside ? onBackRef : onDismissRef).current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [drawer, hidden]);
  // While the drawer shows, what else lies at the window's right makes room for it (`askPage.css`): the results page's
  // Filters and the batch job's panel, which it would otherwise cover, still in the tab order (the lane review).
  useLayoutEffect(() => {
    if (!drawer || hidden) return;
    document.documentElement.setAttribute(BESIDE_DRAWER, "");
    return () => document.documentElement.removeAttribute(BESIDE_DRAWER);
  }, [drawer, hidden]);
  // A change of shape keeps the scroll on the item that was at the top, and moves focus: Expand to the page's heading,
  // where a keyboard user hears where they are; *Show as a drawer* to Expand, the control that undoes it.
  const anchor = useRef<ScrollAnchor | null>(null);
  const shownForm = useRef(form);
  useLayoutEffect(() => {
    if (shownForm.current === form) return;
    shownForm.current = form;
    restoreAnchor(anchor.current, drawer ? body.current : section.current);
    anchor.current = null;
    // Without scrolling: the page's heading is at its top, and focusing it would undo the scroll just kept.
    (drawer ? expandButton.current : heading.current)?.focus({ preventScroll: true });
  }, [form, drawer]);
  const changeShape = (change?: () => void) => () => {
    anchor.current = anchorAtTop(scroller(), body.current);
    change?.();
  };
  const className = drawer
    ? "drawer ask-drawer"
    : govuk
      ? "ask-page ask-page--govuk"
      : "ask-page";
  // Each child keeps its place in both shapes (null where a shape has none), so the body is never mounted again.
  return (
    <section
      ref={section}
      className={className}
      role={drawer ? "dialog" : undefined}
      aria-labelledby="ask-page-title"
      tabIndex={drawer ? -1 : undefined}
      hidden={hidden}
      style={drawer && top !== null ? { top } : undefined}
    >
      {drawer ? null : (
        <button type="button" className={govuk ? "govuk-back-link ask-page__back" : "ask-page__back"} onClick={onBack}>
          {`Back to ${backLabel}`}
        </button>
      )}
      <div className={drawer ? "panel__title drawer__title ask-surface__head" : "ask-surface__head"}>
        <h2
          id="ask-page-title"
          ref={heading}
          tabIndex={-1}
          className={drawer ? "ask-drawer__title" : govuk ? "govuk-heading-l" : "ask-page__title"}
        >
          Ask & Chat
        </h2>
        {drawer ? (
          <span className="ask-surface__actions">
            <button
              type="button"
              ref={expandButton}
              className="btn btn--quiet"
              aria-label="Expand Ask & Chat to the full page"
              onClick={changeShape(onExpand)}
            >
              Expand
            </button>
            <button type="button" className="btn btn--quiet" aria-label="Close Ask & Chat" onClick={onBack}>
              Close
            </button>
          </span>
        ) : (
          <button
            type="button"
            className={govuk ? "govuk-button govuk-button--secondary ask-page__shape" : "btn btn--quiet ask-page__shape"}
            onClick={changeShape(onCollapse)}
          >
            Show as a drawer
          </button>
        )}
      </div>
      {beside}
      <div ref={body} className={drawer ? "panel__body ask-page__body" : "ask-page__body"}>
        {children}
      </div>
    </section>
  );
}
