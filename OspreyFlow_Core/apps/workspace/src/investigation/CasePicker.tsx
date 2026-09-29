// The screen shown before the workspace opens (ADR-052 §9): the cases this account holds a level
// on, by name, and a way to start a new one. The Glass used to create an empty case on every load,
// which is why a signed-in analyst saw "0 nodes" and no way to reach the data they had.
import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Panel } from "../design/primitives/Panel";
import { type CaseListing, caseLabel, listCases, orderCases } from "./cases";
import { NewCaseForm } from "./NewCaseForm";

export interface CasePickerProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** The case last opened in this browser tab, marked in the list. */
  lastCaseId: string | null;
  onOpen: (id: string) => void;
}

export function CasePicker({ apiBaseUrl, bearerToken, lastCaseId, onOpen }: CasePickerProps) {
  const [cases, setCases] = useState<CaseListing[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((listed) => {
        if (!cancelled) setCases(listed);
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          setError(failure instanceof Error ? failure.message : "Could not load your cases.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        padding: "var(--sp-24)",
        minHeight: "100vh",
      }}
    >
      <div style={{ width: "min(720px, 100%)", display: "flex", flexDirection: "column", gap: "var(--sp-16)" }}>
        <h1>Choose a case</h1>
        <Panel>
          {error && <p role="alert">{error}</p>}
          {!error && cases === null && <p className="label">Loading your cases…</p>}
          {!error && cases !== null && cases.length === 0 && (
            <p className="label">You have no cases yet. Create one to begin.</p>
          )}
          {cases !== null && cases.length > 0 && (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {orderCases(cases).map((entry) => (
                <li
                  key={entry.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "var(--sp-16)",
                    padding: "var(--sp-8) 0",
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                >
                  <Button onClick={() => onOpen(entry.id)}>{caseLabel(entry)}</Button>
                  <span className="label">
                    {entry.id === lastCaseId ? "Last opened · " : ""}
                    {entry.level}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel>
          <h2>New case</h2>
          <NewCaseForm
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            inputLabel="Case name"
            onCreated={onOpen}
          />
        </Panel>
      </div>
    </div>
  );
}
