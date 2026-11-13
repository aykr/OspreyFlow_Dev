// *Views ▾* by the graph (ADR-144 Amendment 3, the owner's ruling of 13 November 2026): the open case's
// saved views one click from the canvas, in the canvas toolbar's View group beside *Clear view*. It reads
// what the Cases drawer's *Views in this case* reads (`listViews`, read again each time it opens), so it
// shows exactly the views this reader may see: the Conduit sends no other (rule 3), and the menu draws
// what it is given. Choosing one is the caller's `onOpen`, the same `openLens` as the drawer's *Open*.
// Sharing and deleting stay in the drawer, whose list is kept.
import { useEffect, useId, useRef, useState } from "react";

import { type CaseView, listViews } from "./viewsApi";

export interface ViewsMenuProps {
  apiBaseUrl: string;
  bearerToken: string;
  caseId: string;
  /** The view open now, if one is, marked as the current item. */
  openViewId?: string | null;
  onOpen: (view: CaseView) => void;
}

export const NO_VIEWS_YET = "No saved views yet. Select nodes and choose Save as a view.";

export function ViewsMenu({ apiBaseUrl, bearerToken, caseId, openViewId = null, onOpen }: ViewsMenuProps) {
  const [open, setOpen] = useState(false);
  const [views, setViews] = useState<CaseView[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    let live = true;
    setViews(null);
    setProblem(null);
    listViews(apiBaseUrl, bearerToken, caseId)
      .then((listed) => live && setViews(listed))
      .catch((failure: unknown) => {
        if (!live) return;
        setViews([]);
        setProblem(failure instanceof Error ? failure.message : "The views could not be loaded.");
      });
    const onPointerDown = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as globalThis.Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      live = false;
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, apiBaseUrl, bearerToken, caseId]);

  return (
    <div
      // A segment of the canvas toolbar's View group, its panel laid over the canvas below it.
      className="canvas-menu"
      ref={wrapper}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          button.current?.focus();
        }
      }}
      onBlur={(event) => {
        const next = event.relatedTarget as globalThis.Node | null;
        if (open && next && wrapper.current && !wrapper.current.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={button}
        type="button"
        className="radial-menu__item"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title="Open one of this case's saved views"
        onClick={() => setOpen((was) => !was)}
      >
        Views <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div id={panelId} role="group" aria-label="Saved views in this case" className="canvas-menu-panel canvas-menu-panel--end views-menu">
          {views === null ? (
            <span className="caption">Loading the views…</span>
          ) : views.length === 0 && !problem ? (
            <span>{NO_VIEWS_YET}</span>
          ) : (
            <ul className="views-menu__list">
              {views.map((view) => (
                <li key={view.id}>
                  <button
                    type="button"
                    className="menu-panel__item views-menu__item"
                    aria-current={view.id === openViewId ? "true" : undefined}
                    onClick={() => {
                      setOpen(false);
                      onOpen(view);
                    }}
                  >
                    <span className="views-menu__name">{view.name}</span>
                    <span className={view.shared ? "view-tag view-tag--shared" : "view-tag"}>{view.shared ? "Shared" : "Private"}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {problem && (
            <p role="alert" className="case-views__problem">
              {problem}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
