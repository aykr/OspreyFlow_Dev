// Over the canvas while a view is open (the owner's ruling of 8 November 2026, ADR-144 Amendment 2):
// which view, whether anything in it could not be shown (a count, never which or why: ADR-144
// decision 2), that nothing in it changes the case, and the way back to the case.
import "./views.css";

import { useEffect, useRef } from "react";

import { currentBrand } from "../brand/brand";
import { missingNote } from "./viewsApi";

export interface ViewLensBannerProps {
  name: string;
  shared: boolean;
  missing: number;
  onBack: () => void;
}

export function ViewLensBanner({ name, shared, missing, onBack }: ViewLensBannerProps) {
  const govuk = currentBrand() === "govuk";
  const note = missingNote(missing);
  // Focus comes here when the view opens, wherever it was asked for (the Cases drawer, the over-cap
  // dialog that has just closed), so a keyboard user is never left on the page body.
  const back = useRef<HTMLButtonElement>(null);
  useEffect(() => back.current?.focus(), []);
  return (
    <div role="region" aria-label="Open view" className="view-lens-banner">
      <span>
        View: <span className="view-lens-banner__name">{name}</span>
      </span>
      <span className={govuk ? `govuk-tag ${shared ? "govuk-tag--green" : "govuk-tag--grey"}` : shared ? "view-tag view-tag--shared" : "view-tag"}>
        {shared ? "Shared" : "Private"}
      </span>
      {note && <span className="view-lens-banner__note">{note}</span>}
      <span className="view-lens-banner__note">Nothing in a view changes the case.</span>
      <button ref={back} type="button" className={govuk ? "govuk-button govuk-button--secondary view-lens-banner__back" : "btn view-lens-banner__back"} onClick={onBack}>
        Back to the case
      </button>
    </div>
  );
}
