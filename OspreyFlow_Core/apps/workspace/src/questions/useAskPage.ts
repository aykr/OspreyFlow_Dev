// Ask & Chat, a drawer by default with Expand to a page over the view (ADR-145 Amendment 20, v0.6.1; the page is
// Amendment 18's): whether it is open and in which shape, where focus goes, and what is out of reach, as
// `search/useSearchResultsOverlay.ts` is for the results page. `App.tsx` and the keyboard harnesses
// (`keyboard/places-harness.tsx`, `keyboard/questions-harness.tsx`, `keyboard/harness.tsx`,
// `keyboard/search-results-harness.tsx`) all use this, so the harnesses' cases prove the App's behaviour, not a copy.
import { useEffect, useRef, useState } from "react";

import { RAIL_LABELS } from "../shell/railLayout";
import { focusRailOpener } from "../shell/LeftRail";

/** Ask & Chat's heading, to which focus goes when a document read from an answer closes. */
const ASK_HEADING = "#ask-page-title";
/** The graph's canvas, to which focus goes when a marker leaves Ask & Chat for it. */
const CANVAS = '[role="application"][aria-label="Network canvas"]';

/** What the results page offers this hook: leaving them, so the results and Ask & Chat's page replace each other. */
export interface OtherPage {
  leave: () => void;
}

/** The two shapes (Amendment 20): beside the view, or filling the main area over it. */
export type AskForm = "drawer" | "page";

export interface AskPageState {
  open: boolean;
  /** Open as the page (Expand, or the results' Ask line); false while it is the drawer or closed. */
  expanded: boolean;
  /** Open and drawn: not hidden for a document read from an answer. What the rail's opener marks as expanded. */
  shown: boolean;
  /** The rail's Ask & Chat, *Ask the model about these…*: the drawer, beside whatever is shown. Each opening is the
   * drawer, the shape last used not remembered (Amendment 20 decision 4); already open (hidden for a document read
   * from an answer), it is shown again in the shape it had. */
  openDrawer: () => void;
  /** The results' Ask line: the page, which replaces the results (Amendment 18 point 3). */
  openPage: () => void;
  /** The drawer's Expand: the page, the results left; the panel itself is kept (never mounted again). */
  expand: () => void;
  /** The page's *Show as a drawer*: the drawer (focus on its Expand: `AskPage`). */
  collapse: () => void;
  /** *Back to ‹view›*, the drawer's Close or Escape, or the rail's second press: closed entirely, focus on the rail's
   * Ask & Chat. */
  back: () => void;
  /** The rail's Ask & Chat: closes Ask & Chat when it shows; otherwise `openDrawer` (the reader closed, focus on its
   * heading), in one press. */
  toggle: () => void;
  /** A search: the results take the page's place; the drawer stays beside them. */
  leave: () => void;
  /** A view or a saved view chosen: the results and the page are left; the drawer stays beside the new view, as
   * Explore and History do. */
  viewChosen: () => void;
  /** Leaving the Glass (another place, the cross-link): the results, and Ask & Chat in either shape. */
  leaveBoth: () => void;
  /** A marker in an answer: Ask & Chat closed, then `show` run once the view is back in reach, and focus to the
   * canvas. */
  showOnGraph: (show: () => void) => void;
  /** The view beneath is out of reach while the page shows over it (never for the drawer, which lies beside it). */
  viewInert: boolean;
  /** Kept, not drawn, while a document read from an answer is open over the view. */
  pageHidden: boolean;
}

/** `reading`: a document is open in the reader over the view (Ask & Chat is hidden, the view in reach). `stopReading`
 * closes it: Ask & Chat, opened while a document is read, takes its place and shows at once (the orchestrator,
 * 15 November 2026), as the results page does. `initial`: open at once, in that shape (a case opened on its
 * questions, ADR-098 decision 4, opens the drawer). */
export function useAskPage(
  reading: boolean,
  other: OtherPage,
  initial: AskForm | null = null,
  stopReading?: () => void,
): AskPageState {
  const [open, setOpen] = useState(initial !== null);
  const [expanded, setExpanded] = useState(initial === "page");
  // A document read from an answer has closed: focus goes back to Ask & Chat, never to the view beneath.
  // Not when Ask & Chat itself closed the reader on opening: its own opening says where focus goes.
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
  const closeReader = () => {
    if (reading && stopReading) {
      // Ask & Chat already open (hidden for the reader) is not drawn again, so its own opening focuses nothing: the
      // effect above takes focus to its heading as the reader closes. Opening now focuses its heading itself.
      if (!open) openedOverReader.current = true;
      stopReading();
      // The drawer leaves the results in place, and their hook takes focus to their heading as the reader closes,
      // after Ask & Chat's own opening did: Ask & Chat was asked for, so its heading has it, once those have run.
      setTimeout(() => document.querySelector<HTMLElement>(ASK_HEADING)?.focus(), 0);
    }
  };
  const openDrawer = () => {
    closeReader();
    if (!open) setExpanded(false);
    setOpen(true);
  };
  const close = () => {
    setOpen(false);
    setExpanded(false);
  };
  const back = () => {
    // The rail sits outside Ask & Chat and the inert view, so its opener takes focus at once, before Ask & Chat goes.
    focusRailOpener(RAIL_LABELS.questions);
    close();
  };
  const leavePage = () => {
    if (expanded) close();
  };
  return {
    open,
    expanded: open && expanded,
    shown: open && !reading,
    openDrawer,
    openPage: () => {
      other.leave();
      closeReader();
      setExpanded(true);
      setOpen(true);
    },
    expand: () => {
      other.leave();
      setExpanded(true);
    },
    collapse: () => setExpanded(false),
    back,
    toggle: () => (open && !reading ? back() : openDrawer()),
    leave: leavePage,
    viewChosen: () => {
      other.leave();
      leavePage();
    },
    leaveBoth: () => {
      other.leave();
      close();
    },
    showOnGraph: (show) => {
      close();
      other.leave();
      // Once Ask & Chat has gone and the view is back in reach: never left on the marker that went with it.
      setTimeout(() => {
        show();
        document.querySelector<HTMLElement>(CANVAS)?.focus();
      }, 0);
    },
    viewInert: open && expanded && !reading,
    pageHidden: reading,
  };
}
