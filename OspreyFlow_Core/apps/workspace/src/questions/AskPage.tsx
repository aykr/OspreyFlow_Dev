// Ask & Chat as a page (v0.6.0 #4, the owner's list; the orchestrator's rulings, 15 November 2026): it fills the main
// area over the view the person left, as the search results page does (`search/SearchResults.tsx`), with a back link
// to that view at its start (GOV.UK's back link under that brand). The view beneath stays as it was and is out of
// reach (`inert`) while the page shows. Opening it takes focus to its heading; Back gives the view back, focus on the
// rail's Ask & Chat. The results page and this one replace each other (`App.tsx`). Explore and History stay drawers.
import { type ReactNode, useEffect, useRef } from "react";

import { currentBrand } from "../brand/brand";
import "./askPage.css";

export interface AskPageProps {
  /** The name of the view the person left ("Graph"), for the back link. */
  backLabel: string;
  onBack: () => void;
  /** Kept, not drawn, while a document read from an answer is open over the view. */
  hidden?: boolean;
  /** Help's keys panel, when asked for, over the page rather than beneath it. */
  beside?: ReactNode;
  /** Focus to the heading on opening; false when the page opens with words carried into the question, whose box
   * takes focus instead (the results page's *Ask a question about '…' instead*). */
  takeFocus?: boolean;
  children: ReactNode;
}

export function AskPage({ backLabel, onBack, hidden = false, beside = null, takeFocus = true, children }: AskPageProps) {
  const govuk = currentBrand() === "govuk";
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (takeFocus) heading.current?.focus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- on opening only
  return (
    <section className={govuk ? "ask-page ask-page--govuk" : "ask-page"} aria-labelledby="ask-page-title" hidden={hidden}>
      <button type="button" className={govuk ? "govuk-back-link ask-page__back" : "ask-page__back"} onClick={onBack}>
        {`Back to ${backLabel}`}
      </button>
      <h2 id="ask-page-title" ref={heading} tabIndex={-1} className={govuk ? "govuk-heading-l" : "ask-page__title"}>
        Ask & Chat
      </h2>
      {beside}
      <div className="ask-page__body">{children}</div>
    </section>
  );
}
