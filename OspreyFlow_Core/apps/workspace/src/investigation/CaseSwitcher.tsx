// The current case, by name, with a way to move to another or start a new one. Used in the
// Glass header and at the top of the Ingest Studio, where the owner asked to choose the case data
// is loaded into (29 September 2026).
import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Select } from "../design/primitives/Select";
import { type CaseListing, caseLabel, listCases, orderCases } from "./cases";
import { NewCaseForm } from "./NewCaseForm";

export interface CaseSwitcherProps {
  apiBaseUrl: string;
  bearerToken: string;
  currentId: string;
  onOpen: (id: string) => void;
}

export function CaseSwitcher({ apiBaseUrl, bearerToken, currentId, onOpen }: CaseSwitcherProps) {
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

  const known = cases.some((entry) => entry.id === currentId);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)", flexWrap: "wrap" }}>
      <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        <span className="label">Case</span>
        <Select
          value={currentId}
          onChange={(event) => {
            if (event.target.value !== currentId) onOpen(event.target.value);
          }}
        >
          {!known && <option value={currentId}>Current case</option>}
          {orderCases(cases).map((entry) => (
            <option key={entry.id} value={entry.id}>
              {caseLabel(entry)}
            </option>
          ))}
        </Select>
      </label>
      {!creating && <Button onClick={() => setCreating(true)}>New case</Button>}
      {creating && (
        <NewCaseForm
          apiBaseUrl={apiBaseUrl}
          bearerToken={bearerToken}
          inputLabel="New case name"
          onCreated={onOpen}
        />
      )}
    </div>
  );
}
