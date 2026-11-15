// Ask & Chat as a page over the view (ADR-145 Amendment 18, v0.6.0 #4): when it shows, where focus goes, and what is
// out of reach, as `search/useSearchResultsOverlay.ts` is for the results page. `App.tsx` and the keyboard harnesses
// (`keyboard/places-harness.tsx`, `keyboard/questions-harness.tsx`) all use this, so the harnesses' cases prove the
// App's behaviour, not a copy of it.
import { useEffect, useRef, useState } from "react";

import { RAIL_LABELS } from "../shell/railLayout";
import { focusRailOpener } from "../shell/LeftRail";

/** The page's heading, to which focus goes when a document read from an answer closes. */
const ASK_HEADING = "#ask-page-title";
/** The graph's canvas, to which focus goes when a marker leaves the page for it. */
const CANVAS = '[role="application"][aria-label="Network canvas"]';

/** What the results page offers this hook: leaving them, so the two pages replace each other. */
export interface OtherPage {
  leave: () => void;
}

export interface AskPageState {
  open: boolean;
  /** Open and drawn: not hidden for a document read from an answer. What the rail's opener marks as expanded. */
  shown: boolean;
  /** The rail's Ask & Chat, the results' Ask line, *Ask the model about these…*: leaves the results for the page. */
  openPage: () => void;
  /** *Back to ‹view›*, or the rail's second press: the view as it was, focus on the rail's Ask & Chat. */
  back: () => void;
  /** The rail's Ask & Chat: goes back from the page when it shows; otherwise opens it, or shows it again when it is
   * hidden for a document read from an answer (the reader closed, focus on its heading), in one press. */
  toggle: () => void;
  /** A search, which shows the results in the page's place. */
  leave: () => void;
  /** Anything that leaves both pages (a view chosen, another place, a saved view, the cross-link). */
  leaveBoth: () => void;
  /** A marker in an answer: the page left, then `show` run once the view is back in reach, and focus to the canvas. */
  showOnGraph: (show: () => void) => void;
  /** The view beneath is out of reach while the page shows over it. */
  viewInert: boolean;
  /** Kept, not drawn, while a document read from an answer is open over the view. */
  pageHidden: boolean;
}

/** `reading`: a document is open in the reader over the view (the page is hidden, the view in reach). `stopReading`
 * closes it: the page, opened while a document is read, takes the view's place and shows at once (the orchestrator,
 * 15 November 2026), as the results page does. */
export function useAskPage(reading: boolean, other: OtherPage, initial = false, stopReading?: () => void): AskPageState {
  const [open, setOpen] = useState(initial);
  // A document read from an answer has closed: focus goes back to the page, never to the view beneath (inert again).
  // Not when the page itself closed the reader on opening: the page's own opening says where focus goes.
  const wasReading = useRef(reading);
  const openedOverReader = useRef(false);
  useEffect(() => {
    const was = wasReading.current;
    wasReading.current = reading;
    if (openedOverReader.current) {
      openedOverReader.current = false;
      return;
    }
    if (was && !reading && open) document.querySelector<HTMLElement>(ASK_HEADING)?.focus();
  }, [reading, open]);
  const openPage = () => {
    other.leave();
    if (reading && stopReading) {
      // A page already open (hidden for the reader) is not drawn again, so its own opening focuses nothing: the effect
      // above takes focus to its heading as the reader closes. A page opening now focuses its heading itself.
      if (!open) openedOverReader.current = true;
      stopReading();
    }
    setOpen(true);
  };
  const back = () => {
    // The rail sits outside the page and the inert view, so its opener takes focus at once, before the page goes.
    focusRailOpener(RAIL_LABELS.questions);
    setOpen(false);
  };
  return {
    open,
    openPage,
    back,
    shown: open && !reading,
    toggle: () => (open && !reading ? back() : openPage()),
    leave: () => setOpen(false),
    leaveBoth: () => {
      other.leave();
      setOpen(false);
    },
    showOnGraph: (show) => {
      setOpen(false);
      other.leave();
      // Once the page has gone and the view is back in reach: never left on the marker that went with it.
      setTimeout(() => {
        show();
        document.querySelector<HTMLElement>(CANVAS)?.focus();
      }, 0);
    },
    viewInert: open && !reading,
    pageHidden: reading,
  };
}
