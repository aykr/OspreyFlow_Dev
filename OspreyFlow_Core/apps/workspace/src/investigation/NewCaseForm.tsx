import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { type Dataset, createCase, listDatasets } from "./cases";
import { DatasetChoice } from "./DatasetChoice";

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
  // ADR-099: the datasets the new case reads. None ticked, it gets a dataset of its own.
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    listDatasets(apiBaseUrl, bearerToken)
      .then((found) => !cancelled && setDatasets(found))
      .catch(() => !cancelled && setDatasets([]));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const created = await createCase(apiBaseUrl, bearerToken, name, chosen);
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
      <div style={{ flexBasis: "100%", display: "grid", gap: "var(--sp-4)" }}>
        <DatasetChoice
          datasets={datasets}
          chosen={chosen}
          onChange={setChosen}
          legend="Data the case reads"
          disabled={busy}
        />
        <span className="label">
          {chosen.length === 0
            ? "None ticked: the case gets a dataset of its own, for the data you add to it."
            : "The case reads only these. Its Author can change this later."}
        </span>
      </div>
      {error && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {error}
        </span>
      )}
    </form>
  );
}
