// One tree of cases (ADR-084 Amendment 4; the owner, 14 October 2026: "the current display method for
// the Branch and main case is very confusing, i need a method to delete a branch as through the Glass
// view"). Each case is listed once, with its branches beneath it, named for what they hold and when
// they were made; a branch's row opens it, and its ⋯ offers Rename and Delete in place — Delete asked
// once, and deleting the branch you are in takes you back to the case it came from. Used in the case
// menu and the rail's Cases drawer alike, so the two never disagree.
//
// It enforces nothing: the Conduit decides who may rename (an Author) or remove (an Author, or an
// administrator of the case's unit) a case (ADR-052).
import { useEffect, useState } from "react";

import { type CaseListing, branchLabel, caseLabel, listCases, nestCases, removeCase, renameCase, returnFor } from "./cases";

export interface CaseTreeProps {
  apiBaseUrl: string;
  bearerToken: string;
  currentId: string;
  onOpen: (id: string) => void;
  /** An administrator of the unit may delete any branch in it; the Conduit decides. */
  isAdministrator?: boolean;
  /** The list, when the caller has already fetched it (the case menu has). */
  cases?: CaseListing[];
}

const LEVEL: Record<CaseListing["level"], string> = { author: "Author", editor: "Editor", viewer: "Viewer" };

type Doing = { id: string; what: "menu" | "rename" | "delete" } | null;

export function CaseTree({ apiBaseUrl, bearerToken, currentId, onOpen, isAdministrator = false, cases: given }: CaseTreeProps) {
  const [cases, setCases] = useState<CaseListing[]>(given ?? []);
  const [doing, setDoing] = useState<Doing>(null);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

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

  async function remove(entry: CaseListing): Promise<void> {
    const back = returnFor(cases, entry.id);
    try {
      await removeCase(apiBaseUrl, bearerToken, entry.id);
    } catch (failure: unknown) {
      setProblem(failure instanceof Error ? failure.message : "The branch could not be deleted.");
      return;
    }
    setProblem(null);
    setDoing(null);
    setCases((current) => current.filter((c) => c.id !== entry.id));
    if (entry.id === currentId && back) onOpen(back.id);
  }

  async function rename(entry: CaseListing): Promise<void> {
    const name = draft.trim();
    if (!name) return;
    try {
      await renameCase(apiBaseUrl, bearerToken, entry.id, name);
    } catch (failure: unknown) {
      setProblem(failure instanceof Error ? failure.message : "The branch could not be renamed.");
      return;
    }
    setProblem(null);
    setDoing(null);
    setCases((current) => current.map((c) => (c.id === entry.id ? { ...c, name } : c)));
  }

  if (cases.length === 0) return null;
  return (
    <div className="case-tree">
      <ul aria-label="Cases and their branches" className="case-tree__list">
        {nestCases(cases).map(({ entry, branch }) => {
          const label = branch ? branchLabel(entry) : caseLabel(entry);
          const here = entry.id === currentId;
          const open = doing?.id === entry.id ? doing.what : null;
          const mayRename = entry.level === "author";
          const mayDelete = entry.level === "author" || isAdministrator;
          return (
            <li key={entry.id} data-kind={branch ? "branch" : "case"} className={branch ? "case-tree__row case-tree__row--branch" : "case-tree__row"}>
              <span className="case-tree__line">
                <button
                  type="button"
                  className="case-tree__name"
                  aria-current={here ? "page" : undefined}
                  title={entry.name}
                  onClick={() => !here && onOpen(entry.id)}
                >
                  {branch && <span aria-hidden="true">⑂ </span>}
                  {label}
                </button>
                <span className="case-tree__meta">{here ? "you are here" : branch ? "" : LEVEL[entry.level]}</span>
                {branch && (
                  <button
                    type="button"
                    className="case-tree__more"
                    aria-label={`Actions for ${label}`}
                    aria-expanded={open !== null}
                    onClick={() => setDoing(open ? null : { id: entry.id, what: "menu" })}
                  >
                    ⋯
                  </button>
                )}
              </span>
              {open === "menu" && (
                <span className="case-tree__actions">
                  {!here && (
                    <button type="button" className="menu-panel__item" onClick={() => onOpen(entry.id)}>
                      Open
                    </button>
                  )}
                  {mayRename && (
                    <button
                      type="button"
                      className="menu-panel__item"
                      onClick={() => {
                        setDraft(entry.name.startsWith("Branch of ") ? "" : entry.name);
                        setDoing({ id: entry.id, what: "rename" });
                      }}
                    >
                      Rename
                    </button>
                  )}
                  {mayDelete && (
                    <button type="button" className="menu-panel__item" onClick={() => setDoing({ id: entry.id, what: "delete" })}>
                      Delete
                    </button>
                  )}
                </span>
              )}
              {open === "rename" && (
                <span className="case-tree__actions">
                  <input
                    aria-label="Branch name"
                    className="input"
                    value={draft}
                    autoFocus
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void rename(entry);
                      }
                      if (e.key === "Escape") {
                        e.preventDefault();
                        setDoing(null);
                      }
                    }}
                  />
                  <button type="button" className="menu-panel__item" disabled={!draft.trim()} onClick={() => void rename(entry)}>
                    Save
                  </button>
                  <button type="button" className="menu-panel__item" onClick={() => setDoing(null)}>
                    Cancel
                  </button>
                </span>
              )}
              {open === "delete" && (
                <span className="case-tree__actions case-tree__actions--confirm">
                  <span>
                    Delete this branch? It leaves every list for everyone; the case it came from is untouched.
                  </span>
                  <button type="button" className="menu-panel__item case-tree__danger" onClick={() => void remove(entry)}>
                    Delete branch
                  </button>
                  <button type="button" className="menu-panel__item" onClick={() => setDoing(null)}>
                    Cancel
                  </button>
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {problem && <p role="alert" className="case-tree__problem">{problem}</p>}
    </div>
  );
}
