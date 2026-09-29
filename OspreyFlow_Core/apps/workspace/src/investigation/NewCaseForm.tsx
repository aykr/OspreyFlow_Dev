import { useState } from "react";

import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { createCase } from "./cases";

export interface NewCaseFormProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** Label of the input, so a screen with two of them can tell them apart. */
  inputLabel: string;
  onCreated: (id: string) => void;
}

export function NewCaseForm({ apiBaseUrl, bearerToken, inputLabel, onCreated }: NewCaseFormProps) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const created = await createCase(apiBaseUrl, bearerToken, name);
      onCreated(created.id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the case.");
      setBusy(false);
    }
  }

  return (
    <form
      style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim() && !busy) void create();
      }}
    >
      <Input
        aria-label={inputLabel}
        placeholder="Name the case"
        value={name}
        maxLength={200}
        onChange={(event) => setName(event.target.value)}
      />
      <Button variant="primary" type="submit" disabled={!name.trim() || busy}>
        Create case
      </Button>
      {error && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {error}
        </span>
      )}
    </form>
  );
}
