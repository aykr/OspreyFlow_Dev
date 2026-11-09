// Over the canvas while a view is open (the owner's ruling of 8 November 2026, ADR-144 Amendment 2):
// which view, whether anything in it could not be shown (a count, never which or why: ADR-144
// decision 2), that nothing in it changes the case, and the way back to the case. A merged drawing's
// view (ADR-143 Amendment 2 decision 7, L3.9) also offers *Notes from the drawing*: what did not
// become data, as the Conduit gave it to this reader (an item they may not see has none).
import "./views.css";

import { useEffect, useRef, useState } from "react";

import { currentBrand } from "../brand/brand";
import { missingNote, type CaseViewOpened } from "./viewsApi";

type Annotation = NonNullable<CaseViewOpened["annotations"]>[number];

export interface ViewLensBannerProps {
  name: string;
  shared: boolean;
  missing: number;
  onBack: () => void;
  /** Where the view was opened from, with its own way back (ADR-146 decision 6: "From alert ‹title› ·
   * ← Back to the alert"), drawn before the way back to the case. */
  from?: { label: string; backLabel: string; onBack: () => void };
  /** A merged drawing's annotations (decision 7); none for any other view. */
  annotations?: readonly Annotation[];
}

export function ViewLensBanner({ name, shared, missing, onBack, from, annotations = [] }: ViewLensBannerProps) {
  const govuk = currentBrand() === "govuk";
  const [notesOpen, setNotesOpen] = useState(false);
  const note = missingNote(missing);
  // Focus comes here when the view opens, wherever it was asked for (the Cases drawer, the over-cap
  // dialog that has just closed), so a keyboard user is never left on the page body.
  const back = useRef<HTMLButtonElement>(null);
  const backFrom = useRef<HTMLButtonElement>(null);
  useEffect(() => (backFrom.current ?? back.current)?.focus(), []);
  return (
    <div role="region" aria-label="Open view" className="view-lens-banner">
      {from && <span className="view-lens-banner__from">{from.label}</span>}
      <span>
        View: <span className="view-lens-banner__name">{name}</span>
      </span>
      <span className={govuk ? `govuk-tag ${shared ? "govuk-tag--green" : "govuk-tag--grey"}` : shared ? "view-tag view-tag--shared" : "view-tag"}>
        {shared ? "Shared" : "Private"}
      </span>
      {note && <span className="view-lens-banner__note">{note}</span>}
      <span className="view-lens-banner__note">Nothing in a view changes the case.</span>
      {from && (
        <button ref={backFrom} type="button" className={govuk ? "govuk-button view-lens-banner__back" : "btn btn--primary view-lens-banner__back"} onClick={from.onBack}>
          {from.backLabel}
        </button>
      )}
      {annotations.length > 0 && (
        <button
          type="button"
          aria-expanded={notesOpen}
          aria-controls="view-drawing-notes"
          className={govuk ? "govuk-button govuk-button--secondary view-lens-banner__notes" : "btn view-lens-banner__notes"}
          onClick={() => setNotesOpen((open) => !open)}
        >
          Notes from the drawing ({annotations.length})
        </button>
      )}
      <button ref={back} type="button" className={govuk ? "govuk-button govuk-button--secondary view-lens-banner__back" : "btn view-lens-banner__back"} onClick={onBack}>
        Back to the case
      </button>
      {notesOpen && annotations.length > 0 && (
        <dl id="view-drawing-notes" className={govuk ? "govuk-summary-list view-drawing-notes" : "view-drawing-notes"}>
          {annotations.map((a) => (
            <div key={a.element_id} className={govuk ? "govuk-summary-list__row" : "view-drawing-notes__row"}>
              <dt className={govuk ? "govuk-summary-list__key" : "view-drawing-notes__label"}>{a.label}</dt>
              <dd className={govuk ? "govuk-summary-list__value" : "view-drawing-notes__value"}>
                {[a.marking, a.grading ? `graded ${a.grading}` : null, a.source_note].filter(Boolean).join(" · ")}
                <br />
                <span className="view-lens-banner__note">{a.words}.</span>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
