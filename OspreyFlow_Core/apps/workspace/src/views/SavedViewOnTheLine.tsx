// ADR-145 Amendment 19 decisions 1–3 (the owner's ruling of 16 November 2026, v0.6.1): what is open is said on the case
// line, which is always drawn, so opening or closing a saved view moves the canvas by nothing. It replaces the strip
// under the line (`ViewLensBanner` and `WholeCaseStrip`, Amendment 17).
//
// With no saved view open the line ends "Whole case". With one open it reads "Saved view: ‹name› [Shared] · Details ▾
// · ← Back to the alert · Back to the whole case": *Details* opens over the canvas and holds what the strip held
// besides (ADR-144 Amendment 2 decision 4): the count of what could not be shown (a count, never which or why, ADR-144
// decision 2), that nothing in a saved view changes the case, where it was opened from with its own way back
// (ADR-146 decision 6), and a merged drawing's *Notes from the drawing (n)* (ADR-143 Amendment 2 decision 7).
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import "./views.css";

import { missingNote, type CaseViewOpened } from "./viewsApi";

type Annotation = NonNullable<CaseViewOpened["annotations"]>[number];

export interface SavedViewOnTheLine {
  /** The saved view's id: focus comes to its name once per view opened. */
  id: string;
  name: string;
  shared: boolean;
  /** How many of its items could not be shown to this reader: a count, never which or why. */
  missing: number;
  /** *Back to the whole case*. */
  onBack: () => void;
  /** Where it was opened from, with its own way back: "From alert ‹title›" and *← Back to the alert*. */
  from?: { label: string; backLabel: string; onBack: () => void };
  /** A merged drawing's annotations; none for any other view. */
  annotations?: readonly Annotation[];
}

/** What the case line says is on the canvas: the whole case, or a saved view. */
export type CaseState = "whole" | SavedViewOnTheLine;

export const DETAILS_ID = "saved-view-details";
export const NOTHING_CHANGES = "Nothing in a saved view changes the case.";

/** The items the state adds to the line, each a flex item of the line itself so the line's fold sees them. */
export function CaseStateItems({
  state,
  govuk,
  sep,
  fitName,
  detailsOpen,
  onDetails,
  detailsButton,
}: {
  state: CaseState;
  govuk: boolean;
  sep: () => ReactNode;
  /** The name gives way, with an ellipsis (the line's fold, after "reads …"). */
  fitName: boolean;
  detailsOpen: boolean;
  onDetails: () => void;
  detailsButton: RefObject<HTMLButtonElement | null>;
}) {
  const named = useRef<HTMLSpanElement>(null);
  const id = state === "whole" ? null : state.id;
  // Opening a saved view moves focus to its name on the line (decision 3), wherever it was asked for (the saved views
  // panel, the over-cap dialog just closed), so a keyboard user hears which is open; *Details* is the next Tab.
  useEffect(() => {
    if (id !== null) named.current?.focus();
  }, [id]);
  if (state === "whole") {
    return (
      <>
        {sep()}
        <span className="context-banner__state">Whole case</span>
      </>
    );
  }
  const tag = govuk ? `govuk-tag ${state.shared ? "govuk-tag--green" : "govuk-tag--grey"}` : state.shared ? "view-tag view-tag--shared" : "view-tag";
  return (
    <>
      {sep()}
      <span
        ref={named}
        tabIndex={-1}
        className={fitName ? "context-banner__state context-banner__saved-view context-banner__fit" : "context-banner__state context-banner__saved-view"}
        title={`Saved view: ${state.name}`}
      >
        Saved view: <span className="context-banner__view-name">{state.name}</span>
      </span>
      <span className={`${tag} context-banner__tag`}>{state.shared ? "Shared" : "Private"}</span>
      {sep()}
      <button
        ref={detailsButton}
        type="button"
        className={govuk ? "govuk-link context-banner__section" : "context-banner__section"}
        aria-expanded={detailsOpen}
        aria-controls={DETAILS_ID}
        onClick={onDetails}
      >
        Details <span aria-hidden="true">▾</span>
      </button>
      {state.from && (
        <>
          {sep()}
          <button type="button" className={govuk ? "govuk-link context-banner__section" : "context-banner__section"} onClick={state.from.onBack}>
            {state.from.backLabel}
          </button>
        </>
      )}
      {sep()}
      {/* The way back: a link's look; under GOV.UK, GOV.UK's back link. The chevron is drawn, never read. */}
      <button type="button" className={govuk ? "govuk-back-link context-banner__whole" : "context-banner__whole"} onClick={state.onBack}>
        {!govuk && <span aria-hidden="true">‹ </span>}
        Back to the whole case
      </button>
    </>
  );
}

/** *Details*, open: over the canvas, under the line's right end, so it moves nothing. It is inside the line, so the
 * line's own Esc (`ContextBanner`) closes it, wherever focus is, and focus goes back to *Details*. */
export function SavedViewDetails({
  state,
  govuk,
  notesOpen: startOpen = false,
}: {
  state: SavedViewOnTheLine;
  govuk: boolean;
  notesOpen?: boolean;
}) {
  const [notesOpen, setNotesOpen] = useState(startOpen);
  const annotations = state.annotations ?? [];
  const note = missingNote(state.missing);
  return (
    <div id={DETAILS_ID} role="region" aria-label="Saved view details" className="case-line-details" data-off-line="">
      <p className="case-line-details__line">
        Saved view: <span className="context-banner__view-name">{state.name}</span>, {state.shared ? "shared" : "private"}
      </p>
      {note && <p className="case-line-details__line">{note}</p>}
      <p className="case-line-details__line case-line-details__quiet">{NOTHING_CHANGES}</p>
      {state.from && (
        <p className="case-line-details__line">
          <span className="case-line-details__from">{state.from.label}</span>{" "}
          <button type="button" className={govuk ? "govuk-link case-line-details__link" : "case-line-details__link"} onClick={state.from.onBack}>
            {state.from.backLabel}
          </button>
        </p>
      )}
      {annotations.length > 0 && (
        <>
          <button
            type="button"
            aria-expanded={notesOpen}
            aria-controls="view-drawing-notes"
            className={govuk ? "govuk-button govuk-button--secondary case-line-details__notes" : "btn case-line-details__notes"}
            onClick={() => setNotesOpen((open) => !open)}
          >
            Notes from the drawing ({annotations.length})
          </button>
          {notesOpen && (
            // The notes scroll when they are many, or tall (GOV.UK's rows): the scrolling box is a named region in the
            // tab order, so a keyboard reaches it and its arrow keys scroll it (WCAG 2.1.1; axe scrollable-region-focusable).
            <div id="view-drawing-notes" role="region" aria-label="Notes from the drawing" tabIndex={0} className="view-drawing-notes__scroll">
            <dl className={govuk ? "govuk-summary-list view-drawing-notes" : "view-drawing-notes"}>
              {annotations.map((a) => (
                <div key={a.element_id} className={govuk ? "govuk-summary-list__row" : "view-drawing-notes__row"}>
                  <dt className={govuk ? "govuk-summary-list__key" : "view-drawing-notes__label"}>{a.label}</dt>
                  <dd className={govuk ? "govuk-summary-list__value" : "view-drawing-notes__value"}>
                    {[a.marking, a.grading ? `graded ${a.grading}` : null, a.source_note].filter(Boolean).join(" · ")}
                    <br />
                    <span className="case-line-details__quiet">{a.words}.</span>
                  </dd>
                </div>
              ))}
            </dl>
            </div>
          )}
        </>
      )}
    </div>
  );
}
