// The search results page over the view (ADR-145 Amendment 15 Part A): when it shows, where focus goes, and what is out
// of reach. `App.tsx` and the keyboard harness (`keyboard/search-results-harness.tsx`) both use this, so the harness's
// cases prove the App's behaviour, not a copy of it.
import { useEffect, useRef, useState } from "react";

/** The top bar's search box, to which Back returns focus. */
export const SEARCH_BOX = '.top-bar [role="combobox"]';
/** The results' heading, to which focus goes when a document read from them closes. */
const RESULTS_HEADING = "section.search-results h2";

export interface SearchShowing {
  query: string;
  /** The view's name the person left ("Graph"), for the back link. */
  left: string;
  /** A new search each time, the same words or not: it asks again and takes focus to the heading. */
  at: number;
}

export interface SearchResultsOverlay {
  searching: SearchShowing | null;
  /** Enter on the typed words. */
  open: (query: string, left: string) => void;
  /** *Back to ‹view›*: the view as it was, focus in the search box. */
  back: () => void;
  /** Anything else that leaves them (a view chosen, *Show on graph*, a saved view opened, another place). */
  leave: () => void;
  /** The view beneath is out of reach while the results show over it. */
  viewInert: boolean;
  /** Kept, not drawn, while a document read from them is open over the view. */
  resultsHidden: boolean;
}

/** `reading`: a document is open in the reader over the view (the results are hidden, the view in reach). */
export function useSearchResultsOverlay(reading: boolean): SearchResultsOverlay {
  const [searching, setSearching] = useState<SearchShowing | null>(null);
  const searches = useRef(0);
  const focusBox = useRef(false);
  useEffect(() => {
    if (searching !== null || !focusBox.current) return;
    focusBox.current = false;
    document.querySelector<HTMLElement>(SEARCH_BOX)?.focus();
  }, [searching]);
  // A document read from the results has closed: focus goes back into them, never to the view beneath (inert again).
  const wasReading = useRef(reading);
  useEffect(() => {
    const was = wasReading.current;
    wasReading.current = reading;
    if (was && !reading && searching !== null) document.querySelector<HTMLElement>(RESULTS_HEADING)?.focus();
  }, [reading, searching]);
  return {
    searching,
    open: (query, left) => {
      searches.current += 1;
      setSearching({ query, left, at: searches.current });
    },
    back: () => {
      focusBox.current = true;
      setSearching(null);
    },
    leave: () => setSearching(null),
    viewInert: searching !== null && !reading,
    resultsHidden: reading,
  };
}
