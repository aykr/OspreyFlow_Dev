// The current case, by name, with a way to move to another or start a new one. Used in the
// Glass header and at the top of the Ingest Studio, where the owner asked to choose the case data
// is loaded into (29 September 2026).
import { useEffect, useState } from "react";

import { DropdownPanel } from "../design/primitives/DropdownPanel";
import { type CaseListing, caseLabel, listCases, orderCases } from "./cases";
import { NewCaseForm } from "./NewCaseForm";

export interface CaseSwitcherProps {
  apiBaseUrl: string;
  bearerToken: string;
  currentId: string;
  onOpen: (id: string) => void;
  /** Show the full list of cases (the picker) over the workspace. Absent: no such button. */
  onBrowse?: () => void;
}

export function CaseSwitcher({
  apiBaseUrl,
  bearerToken,
  currentId,
  onOpen,
  onBrowse,
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
  const currentName = current ? caseLabel(current) : "Current case";
  return (
    <DropdownPanel label={`Case: ${currentName}`} title={currentName} panelLabel="Case menu">
      {(close) => (
        <>
          <div className="menu-panel__list">
            {orderCases(cases).map((entry) => (
              <button
                key={entry.id}
                type="button"
                className="menu-panel__item"
                aria-current={entry.id === currentId ? "true" : undefined}
                onClick={() => {
                  close();
                  if (entry.id !== currentId) onOpen(entry.id);
                }}
              >
                {caseLabel(entry)}
              </button>
            ))}
          </div>
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
  );
}
