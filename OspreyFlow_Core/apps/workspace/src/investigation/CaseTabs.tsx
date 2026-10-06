// The strip of tabs above the workspace (ADR-084). A tab is a saved branch of the case on screen:
// a case of its own, made from some nodes the analyst chose, and kept for them. The original case
// is always the first tab. Closing a tab only hides it from this strip (a flag for this account);
// the Branches menu lists every branch, open or hidden, so the analyst can always see what they are
// working across, and is the one place a branch is discarded (after asking).
//
// It enforces nothing: the Conduit decides who may see, open or discard a case (ADR-050, ADR-052).
// Switching tab opens that case, which reloads the page as every case switch does (`cases.ts`).
import { useCallback, useEffect, useState } from "react";

import { DropdownPanel } from "../design/primitives/DropdownPanel";
import {
  type CaseListing,
  branchFamily,
  caseLabel,
  listCases,
  openTabs,
  removeCase,
  setTabHidden,
} from "./cases";

export interface CaseTabsProps {
  apiBaseUrl: string;
  bearerToken: string;
  currentId: string;
  /** An administrator of the unit may discard any branch in it; the Conduit decides. */
  isAdministrator?: boolean;
  onOpen: (id: string) => void;
  /** As a list, each branch indented beneath its case (ADR-097 Amendment 1), in the rail's Cases. */
  layout?: "strip" | "list";
}

export function CaseTabs({
  apiBaseUrl,
  bearerToken,
  currentId,
  isAdministrator = false,
  onOpen,
  layout = "strip",
}: CaseTabsProps) {
  const [cases, setCases] = useState<CaseListing[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((listed) => {
        if (!cancelled) setCases(listed);
      })
      .catch(() => {
        // The case itself still works without its strip; a failed list must not get in the way.
        if (!cancelled) setCases([]);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

  const mark = useCallback(
    async (id: string, hidden: boolean): Promise<boolean> => {
      try {
        await setTabHidden(apiBaseUrl, bearerToken, id, hidden);
        setCases((current) =>
          current.map((entry) => (entry.id === id ? { ...entry, tab_hidden: hidden } : entry)),
        );
        setProblem(null);
        return true;
      } catch (failure: unknown) {
        setProblem(failure instanceof Error ? failure.message : "The tab could not be changed.");
        return false;
      }
    },
    [apiBaseUrl, bearerToken],
  );

  async function discard(id: string): Promise<void> {
    try {
      await removeCase(apiBaseUrl, bearerToken, id);
      setCases((current) => current.filter((entry) => entry.id !== id));
      setConfirming(null);
      setProblem(null);
    } catch (failure: unknown) {
      setProblem(failure instanceof Error ? failure.message : "The branch could not be discarded.");
    }
  }

  const family = branchFamily(cases, currentId);
  if (!family || family.branches.length === 0) return null;

  const { root, branches } = family;
  const shown = openTabs(family, currentId);
  const openCount = branches.filter((entry) => !entry.tab_hidden || entry.id === currentId).length;

  async function close(entry: CaseListing): Promise<void> {
    const closed = await mark(entry.id, true);
    // Closing the tab you are looking at goes back to the original case rather than leave you on
    // a tab that is no longer in the strip.
    if (closed && entry.id === currentId) onOpen(root.id);
  }

  return (
    <nav aria-label="Case tabs" className={layout === "list" ? "case-tabs case-tabs--list" : "case-tabs"}>
      <button
        type="button"
        className="btn case-tabs__tab"
        aria-current={root.id === currentId ? "page" : undefined}
        onClick={() => root.id !== currentId && onOpen(root.id)}
      >
        {caseLabel(root)}
      </button>
      {shown.map((entry) => {
        const label = caseLabel(entry);
        return (
          <span key={entry.id} className="case-tabs__item">
            <button
              type="button"
              className="btn case-tabs__tab"
              aria-current={entry.id === currentId ? "page" : undefined}
              onClick={() => entry.id !== currentId && onOpen(entry.id)}
            >
              {label}
            </button>
            <button
              type="button"
              className="btn case-tabs__close"
              aria-label={`Close tab ${label}`}
              title="Close this tab. The branch is kept in the Branches list."
              onClick={() => void close(entry)}
            >
              ×
            </button>
          </span>
        );
      })}
      <DropdownPanel
        label={`Branches (${openCount} open of ${branches.length})`}
        panelLabel="Branches"
        title="Every branch of this case: open, hidden, or to discard"
      >
        {(closePanel) => (
          <ul className="case-tabs__list">
            {branches.map((entry) => {
              const label = caseLabel(entry);
              const here = entry.id === currentId;
              const hidden = Boolean(entry.tab_hidden) && !here;
              const canDiscard = !here && (entry.level === "author" || isAdministrator);
              return (
                <li key={entry.id} className="case-tabs__row">
                  <span className="case-tabs__name">{label}</span>
                  <span className="label">{here ? "Current" : hidden ? "Hidden" : "Open"}</span>
                  {!here && (
                    <button
                      type="button"
                      className="menu-panel__item"
                      aria-label={`Open ${label}`}
                      onClick={() => {
                        closePanel();
                        onOpen(entry.id);
                      }}
                    >
                      Open
                    </button>
                  )}
                  {hidden && (
                    <button
                      type="button"
                      className="menu-panel__item"
                      aria-label={`Show tab ${label}`}
                      onClick={() => void mark(entry.id, false)}
                    >
                      Show tab
                    </button>
                  )}
                  {canDiscard &&
                    (confirming === entry.id ? (
                      <>
                        <span className="label">
                          Discard this branch? It leaves every list; nothing is deleted.
                        </span>
                        <button
                          type="button"
                          className="menu-panel__item"
                          onClick={() => void discard(entry.id)}
                        >
                          Confirm discard
                        </button>
                        <button
                          type="button"
                          className="menu-panel__item"
                          onClick={() => setConfirming(null)}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="menu-panel__item"
                        aria-label={`Discard ${label}`}
                        onClick={() => setConfirming(entry.id)}
                      >
                        Discard
                      </button>
                    ))}
                </li>
              );
            })}
          </ul>
        )}
      </DropdownPanel>
      {problem && <span role="alert">{problem}</span>}
    </nav>
  );
}
