// The screen shown before the workspace opens (ADR-052 §9): the cases this account holds a level
// on, by name, and a way to start a new one. The Glass used to create an empty case on every load,
// which is why a signed-in analyst saw "0 nodes" and no way to reach the data they had.
import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Panel } from "../design/primitives/Panel";
import { type CaseListing, caseLabel, listCases, orderCases, removeCase } from "./cases";
import { NewCaseForm } from "./NewCaseForm";

export interface CasePickerProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** The case last opened in this browser tab, marked in the list. */
  lastCaseId: string | null;
  /** An administrator of the unit may remove any case in it (ADR-052 Amendment 7); the Conduit
   * decides, this only decides whether to offer the button. */
  isAdministrator?: boolean;
  /** The case that is open behind this picker, if any, and how to return to it without a reload. */
  openCaseId?: string | null;
  onClose?: () => void;
  onOpen: (id: string) => void;
}

export function CasePicker({
  apiBaseUrl,
  bearerToken,
  lastCaseId,
  isAdministrator = false,
  openCaseId = null,
  onClose,
  onOpen,
}: CasePickerProps) {
  const [cases, setCases] = useState<CaseListing[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removalError, setRemovalError] = useState<string | null>(null);

  async function remove(id: string): Promise<void> {
    setRemovalError(null);
    try {
      await removeCase(apiBaseUrl, bearerToken, id);
      setCases((current) => (current ?? []).filter((entry) => entry.id !== id));
      setConfirming(null);
    } catch (failure: unknown) {
      setRemovalError(failure instanceof Error ? failure.message : "The case could not be removed.");
    }
  }

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
        {onClose && openCaseId && cases?.some((entry) => entry.id === openCaseId) && (
          <div>
            <Button onClick={onClose}>
              Back to{" "}
              {caseLabel(cases.find((entry) => entry.id === openCaseId) as CaseListing)}
            </Button>
          </div>
        )}
        <Panel>
          {error && <p role="alert">{error}</p>}
          {removalError && <p role="alert">{removalError}</p>}
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
                  <span style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
                    <span className="label">
                      {entry.id === lastCaseId ? "Last opened · " : ""}
                      {entry.level}
                    </span>
                    {(entry.level === "author" || isAdministrator) &&
                      (confirming === entry.id ? (
                        <>
                          <span className="label">
                            Remove this case from every list? Nothing is deleted.
                          </span>
                          <Button onClick={() => void remove(entry.id)}>Confirm remove</Button>
                          <Button onClick={() => setConfirming(null)}>Cancel</Button>
                        </>
                      ) : (
                        <Button
                          aria-label={`Remove ${caseLabel(entry)}`}
                          onClick={() => {
                            setRemovalError(null);
                            setConfirming(entry.id);
                          }}
                        >
                          Remove
                        </Button>
                      ))}
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
