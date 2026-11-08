// The cases this account holds a level on, each once (ADR-144 Amendment 1: a case is the only
// container, and no case is made from another), with the views of each case beneath it that this
// reader may see: their own, and those shared with the case (ADR-144 decision 5). A case's row opens
// it; a view's row opens the case on that view, as a lens. Used in the Cases drawer, and without the
// views in the case menu.
//
// It enforces nothing: the Conduit lists the cases this account holds a level on, and for each case
// only the views this reader may see, so another member's private view is never sent here.
import { useEffect, useState } from "react";

import { type CaseView, listViews } from "../views/viewsApi";
import { type CaseListing, caseLabel, listCases, orderCases } from "./cases";

export interface CaseListProps {
  apiBaseUrl: string;
  bearerToken: string;
  currentId: string;
  onOpen: (id: string) => void;
  /** A view was chosen: open its case on it. Absent, or `showViews` false: views are not listed. */
  onOpenView?: (caseId: string, view: CaseView) => void;
  showViews?: boolean;
  /** The list, when the caller has already fetched it (the case menu has). */
  cases?: CaseListing[];
  /** Bumped by the caller after a view is saved, shared or deleted, so the views are read again. */
  refreshKey?: number;
}

const LEVEL: Record<CaseListing["level"], string> = { author: "Author", editor: "Editor", viewer: "Viewer" };

export function CaseList({ apiBaseUrl, bearerToken, currentId, onOpen, onOpenView, showViews = true, cases: given, refreshKey = 0 }: CaseListProps) {
  const [cases, setCases] = useState<CaseListing[]>(given ?? []);
  const [views, setViews] = useState<ReadonlyMap<string, CaseView[]>>(new Map());

  useEffect(() => {
    if (given) {
      setCases(given);
      return;
    }
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((listed) => !cancelled && setCases(listed))
      .catch(() => !cancelled && setCases([]));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, given]);

  const listing = showViews && onOpenView !== undefined;
  const ids = cases.map((c) => c.id).join(" ");
  useEffect(() => {
    if (!listing || ids === "") return;
    let cancelled = false;
    // Each case's views, read separately; a case whose views cannot be read shows none, and says
    // nothing about why.
    void Promise.all(
      ids.split(" ").map(async (id) => [id, await listViews(apiBaseUrl, bearerToken, id).catch(() => [])] as const),
    ).then((pairs) => !cancelled && setViews(new Map(pairs)));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, ids, listing, refreshKey]);

  if (cases.length === 0) return null;
  return (
    <div className="case-tree">
      <ul aria-label="Cases" className="case-tree__list">
        {orderCases(cases).map((entry) => {
          const label = caseLabel(entry);
          const here = entry.id === currentId;
          const its = listing ? (views.get(entry.id) ?? []) : [];
          return (
            <li key={entry.id} data-kind="case" className="case-tree__row">
              <span className="case-tree__line">
                <button
                  type="button"
                  className="case-tree__name"
                  aria-current={here ? "page" : undefined}
                  title={entry.name}
                  onClick={() => !here && onOpen(entry.id)}
                >
                  {label}
                </button>
                <span className="case-tree__meta">{here ? "you are here" : LEVEL[entry.level]}</span>
              </span>
              {its.length > 0 && (
                <ul aria-label={`Views in ${label}`} className="case-tree__list case-tree__views">
                  {its.map((view) => (
                    <li key={view.id} data-kind="view" className="case-tree__row case-tree__row--view">
                      <span className="case-tree__line">
                        <button
                          type="button"
                          className="case-tree__name"
                          title={view.name}
                          aria-label={`Open the view ${view.name} of ${label}`}
                          onClick={() => onOpenView?.(entry.id, view)}
                        >
                          {view.name}
                        </button>
                        <span className="case-tree__meta">{view.shared ? "Shared" : "Private"}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
