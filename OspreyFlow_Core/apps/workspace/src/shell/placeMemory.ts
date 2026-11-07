// ADR-145 decision 2: the cross-link back from the Studio "keeps the case they came from" — the case
// is the open one, which moving between the places never changes — and returns to the Glass's view
// that was last open. One hook, used by `App.tsx` and by the keyboard harness, so the case that proves
// it (`keyboard/shell.spec.ts`) fails when the view is not kept.
import { useRef } from "react";

/** The Glass's view to come back to: `view` whenever it is not the Studio's, else the last that was. */
export function useLastGlassView<V extends string>(view: V, studioView: V, initial: V): () => V {
  const last = useRef<V>(view === studioView ? initial : view);
  if (view !== studioView) last.current = view;
  return () => last.current;
}
