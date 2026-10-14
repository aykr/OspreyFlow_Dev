// The current case, by name, with a way to move to another or start a new one. Used in the
// Glass header and at the top of the Ingest Studio, where the owner asked to choose the case data
// is loaded into (29 September 2026).
import { useEffect, useState } from "react";

import { DropdownPanel } from "../design/primitives/DropdownPanel";
import { type CaseListing, branchLabel, caseLabel, listCases, returnFor, scopeBadge } from "./cases";
import { CaseTree } from "./CaseTree";
import { NewCaseForm } from "./NewCaseForm";

export interface CaseSwitcherProps {
  apiBaseUrl: string;
  bearerToken: string;
  currentId: string;
  onOpen: (id: string) => void;
  /** Show the full list of cases (the picker) over the workspace. Absent: no such button. */
  onBrowse?: () => void;
  /** An administrator of the unit may delete any branch in it (ADR-084 Amendment 4). */
  isAdministrator?: boolean;
}

export function CaseSwitcher({
  apiBaseUrl,
  bearerToken,
  currentId,
  onOpen,
  onBrowse,
  isAdministrator = false,
}: CaseSwitcherProps) {
  const [cases, setCases] = useState<CaseListing[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((listed) => {
        if (!cancelled) setCases(listed);
      })
      .catch(() => {
        // The current case is still shown; a failed list must not hide it.
        if (!cancelled) setCases([]);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

  const current = cases.find((entry) => entry.id === currentId);
  // ADR-084 Amendment 4: on a branch, where it sits — the case it came from, then the branch.
  const parent = current?.branched_from ? returnFor(cases, current.id) : null;
  const currentName = current
    ? current.branched_from
      ? `${parent ? `${caseLabel(parent)} › ` : ""}${branchLabel(current)}`
      : caseLabel(current)
    : "Current case";
  const scope = scopeBadge(current?.datasets);
  return (
    <>
    {/* ADR-097 step 3: the bar shows the case's name alone; "Case:" stays for a screen reader. */}
    <DropdownPanel
      label={
        <>
          <span className="visually-hidden">Case: </span>
          {current?.branched_from ? (
            <span>
              {parent && `${caseLabel(parent)} › `}
              <span aria-hidden="true">⑂ </span>
              {branchLabel(current)}
            </span>
          ) : (
            <span>{currentName}</span>
          )}
        </>
      }
      title={currentName}
      panelLabel="Case menu"
      buttonClassName="menu-button--case"
    >
      {(close) => (
        <>
          {/* ADR-084 Amendment 4: the same tree as the Cases drawer — each case, its branches beneath. */}
          <CaseTree
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            currentId={currentId}
            cases={cases}
            isAdministrator={isAdministrator}
            onOpen={(id) => {
              close();
              onOpen(id);
            }}
          />
          <hr className="menu-panel__rule" />
          {onBrowse && (
            <button
              type="button"
              className="menu-panel__item"
              onClick={() => {
                close();
                onBrowse();
              }}
            >
              All cases
            </button>
          )}
          {!creating && (
            <button type="button" className="menu-panel__item" onClick={() => setCreating(true)}>
              New case
            </button>
          )}
          {creating && (
            <NewCaseForm
              apiBaseUrl={apiBaseUrl}
              bearerToken={bearerToken}
              inputLabel="New case name"
              onCreated={onOpen}
            />
          )}
        </>
      )}
    </DropdownPanel>
    {scope && (
      // ADR-115 Amendment 1 point 5: what the case reads, beside its name; a label, not a control.
      <span className="value case-scope" title={scope.title}>
        <span className="visually-hidden">Reads: </span>
        {scope.text}
      </span>
    )}
    </>
  );
}
