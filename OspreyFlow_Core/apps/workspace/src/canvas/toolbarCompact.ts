// v0.6.1 glass-rows (the owner's rulings 6 and 7, 16 November 2026): the canvas toolbar shows shorter words
// when its own width, not the window's, is under about 1132 px, so it stays one row at 1024 in both looks.
import { createContext } from "react";

/** The toolbar's own width, in CSS pixels, under which its words shorten. */
export const TOOLBAR_COMPACT_BELOW_PX = 1132;

export function isCompactToolbar(width: number): boolean {
  // A width of 0 is a toolbar not laid out (jsdom, a hidden view): not narrow, so the full words stay.
  return width > 0 && width < TOOLBAR_COMPACT_BELOW_PX;
}

/** True while the canvas toolbar is narrow; read by a control the toolbar holds. */
export const CanvasToolbarCompact = createContext(false);
