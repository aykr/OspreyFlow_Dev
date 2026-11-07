// ADR-145 decision 2: the cross-link back from the Studio "keeps the case they came from" and
// returns to the Glass's view that was last open. The case is the open one (`investigation/
// investigationId.ts`), which moving between the places never changes. Choosing another case in the
// Studio reloads the page (`investigation/cases.ts`'s `openCase`), so the view to come back to is
// kept in this tab's `sessionStorage`, not only in memory: after the reload, *Back* still returns to
// it. One hook, used by `App.tsx` and by the keyboard harness, so the case that proves it
// (`keyboard/shell.spec.ts`) fails when the view is not kept.
import { useRef } from "react";

export const LAST_GLASS_VIEW_KEY = "ospreyflow.lastGlassView";

function stored(): string | null {
  try {
    return sessionStorage.getItem(LAST_GLASS_VIEW_KEY);
  } catch {
    return null;
  }
}

function keep(view: string): void {
  try {
    sessionStorage.setItem(LAST_GLASS_VIEW_KEY, view);
  } catch {
    // A tab that refuses storage keeps the view in memory only, until the next reload.
  }
}

/** The Glass's view to come back to: the last of `views` that was open (this tab's, across a
 * reload), else `initial`. A view outside `views` is not kept: Messages (`dossier`) is drawn for one
 * node, which a reload does not keep, so Back returns to the view open before it. */
export function useLastGlassView<V extends string>(view: V, studioView: V, initial: V, views: readonly V[]): () => V {
  const last = useRef<V | null>(null);
  const keeps = (v: string | null): v is V => v !== null && v !== studioView && (views as readonly string[]).includes(v);
  if (last.current === null) {
    const kept = stored();
    last.current = keeps(view) ? view : keeps(kept) ? kept : initial;
  }
  if (keeps(view) && (last.current !== view || stored() !== view)) {
    last.current = view;
    keep(view);
  }
  return () => last.current as V;
}
