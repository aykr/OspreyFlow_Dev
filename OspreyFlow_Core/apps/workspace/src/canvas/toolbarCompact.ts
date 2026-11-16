// v0.6.1 glass-rows (the owner's rulings 6 and 7, 16 November 2026): the canvas toolbar shows shorter words
// when its own width, not the window's, is narrow, so it stays one row at 1024 in both looks. The rulings say about
// 1132 px; measured on the toolbar App draws (Show links among all, Clear the graph, Add files, Details and Hide
// toolbar in the View group; the product's faces; `keyboard/glass-toolbar.spec.ts`), the whole words need 1199 px
// and one gap for Last change, so the line is 1220. The short words fit one row down to 912 px.
import { createContext, useLayoutEffect, useState, type RefObject } from "react";

/** The toolbar's own width, in CSS pixels, under which its words shorten. */
export const TOOLBAR_COMPACT_BELOW_PX = 1220;

export function isCompactToolbar(width: number): boolean {
  // A width of 0 is a toolbar not laid out (jsdom, a hidden view): not narrow, so the full words stay.
  return width > 0 && width < TOOLBAR_COMPACT_BELOW_PX;
}

/** True while the canvas toolbar is narrow; read by a control the toolbar holds. */
export const CanvasToolbarCompact = createContext(false);

/** Whether the element `ref` names is narrow, by the same line: for the Map, whose row is App's, and whose row's column is
 * measured, since a hidden row measures 0 wide (the canvas reports its own, `GlassCanvas`'s `onToolbarCompactChange`). */
export function useCompactWidth(ref: RefObject<HTMLElement | null>): boolean {
  const [compact, setCompact] = useState(false);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver !== "function") return;
    const measure = () => {
      const width = element.getBoundingClientRect().width;
      if (width > 0) setCompact(isCompactToolbar(width));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return compact;
}
