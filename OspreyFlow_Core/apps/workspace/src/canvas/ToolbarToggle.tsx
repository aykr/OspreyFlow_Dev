// v0.6.1 glass-rows C (ADR-145 Amendment 19 decision 6): *Hide toolbar* at the right end of the view's toolbar and
// *Show toolbar* at the right end of the slim case line, in the same place. Each is labelled, never an icon alone, so
// an analyst who hid the toolbar can find it again, and each says what it controls and whether it is shown.
import { forwardRef, useContext } from "react";

import { currentBrand } from "../brand/brand";
import { CanvasToolbarCompact } from "./toolbarCompact";
import { VIEW_TOOLBAR_ID } from "./toolbarVisibility";

export interface ToolbarToggleProps {
  onToggle: () => void;
}

export interface HideToolbarButtonProps extends ToolbarToggleProps {
  /** `row`: in the Map's row of ordinary buttons, drawn as they are; otherwise as the canvas toolbar's quiet items. */
  look?: "toolbar" | "row";
}

/** In the toolbar: on a narrow toolbar its visible word is *Hide*, its name still *Hide toolbar* (the owner's ruling 1). */
export const HideToolbarButton = forwardRef<HTMLButtonElement, HideToolbarButtonProps>(function HideToolbarButton({ onToggle, look = "toolbar" }, ref) {
  const compact = useContext(CanvasToolbarCompact);
  return (
    <button
      ref={ref}
      type="button"
      className={look === "row" ? "btn btn--quiet toolbar-toggle" : "radial-menu__item toolbar-toggle"}
      aria-label="Hide toolbar"
      aria-expanded={true}
      aria-controls={VIEW_TOOLBAR_ID}
      title="Hide toolbar (T on the graph)"
      onClick={onToggle}
    >
      {compact ? "Hide" : "Hide toolbar"}
    </button>
  );
});

/** On the slim case line, drawn in its `end`. Under GOV.UK it is a link's look, as the line's cross-link is. */
export const ShowToolbarButton = forwardRef<HTMLButtonElement, ToolbarToggleProps>(function ShowToolbarButton({ onToggle }, ref) {
  const govuk = currentBrand() === "govuk";
  return (
    <button
      ref={ref}
      type="button"
      className={govuk ? "govuk-link toolbar-toggle toolbar-toggle--show" : "btn btn--ghost toolbar-toggle toolbar-toggle--show"}
      aria-expanded={false}
      aria-controls={VIEW_TOOLBAR_ID}
      title="Show toolbar (T on the graph)"
      onClick={onToggle}
    >
      Show toolbar
    </button>
  );
});
