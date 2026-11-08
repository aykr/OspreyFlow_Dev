import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { RadioGroup } from "../design/primitives/RadioGroup";
import { type Dataset, type DomainPack, createCase, listDatasets } from "./cases";
import { DatasetChoice } from "./DatasetChoice";
import { DomainChoice } from "./DomainChoice";

export interface NewCaseFormProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** Label of the input, so a screen with two of them can tell them apart. */
  inputLabel: string;
  onCreated: (id: string) => void;
  /** Which choice the form opens on; "Make a new dataset" unless a harness asks (ADR-099
   * Amendment 12). */
  initialChoice?: "existing" | "new";
}

export function NewCaseForm({
  apiBaseUrl,
  bearerToken,
  inputLabel,
  onCreated,
  initialChoice = "new",
}: NewCaseFormProps) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // ADR-099 Amendment 12 item 6 (R16): a case reads exactly one dataset, an existing one or a new
  // one named here; there is no third choice. "Make a new dataset" is the default (nothing hidden
  // is ever carried), and leaving "Use an existing dataset" forgets which one was chosen.
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [mode, setMode] = useState<"existing" | "new">(initialChoice);
  const [chosen, setChosen] = useState<string | null>(null);
  const [newDatasetName, setNewDatasetName] = useState("");
  // ADR-126: the case's domain packs, none ticked meaning the POLE core model. Submitting sends the
  // list shown, `[]` included, so the case counts as chosen.
  const [domains, setDomains] = useState<DomainPack[]>([]);

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
      const data = mode === "existing" && chosen ? { datasetId: chosen } : { newDatasetName };
      const created = await createCase(apiBaseUrl, bearerToken, name, data, domains);
      onCreated(created.id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not create the case.");
      setBusy(false);
    }
  }

  const ready = Boolean(name.trim()) && !busy && (mode === "new" || chosen !== null);

  return (
    <form
      style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) void create();
      }}
    >
      <Input
        aria-label={inputLabel}
        placeholder="Name the case"
        value={name}
        maxLength={200}
        onChange={(event) => setName(event.target.value)}
      />
      <Button variant="primary" type="submit" disabled={!ready}>
        Create case
      </Button>
      <div style={{ flexBasis: "100%", display: "grid", gap: "var(--sp-8)" }}>
        <span className="label">What data does this case read?</span>
        <RadioGroup
          name="new-case-data"
          aria-label="What data does this case read?"
          value={mode}
          onChange={(value) => {
            setMode(value as "existing" | "new");
            if (value === "new") setChosen(null);
          }}
          options={[
            { value: "existing", label: "Use an existing dataset…" },
            { value: "new", label: "Make a new dataset — empty, loaded in the Ingest Studio" },
          ]}
        />
        <div style={{ display: "grid", gap: "var(--sp-4)", paddingLeft: "var(--sp-24)" }}>
          {mode === "existing" ? (
            <DatasetChoice
              name="new-case-dataset"
              datasets={datasets}
              chosen={chosen}
              onChange={setChosen}
              legend="The case reads this dataset only; its Author can change it later."
            />
          ) : (
            <Input
              aria-label="Name of the new dataset"
              placeholder={name.trim() ? `Left empty: ${name.trim()}` : "Name the new dataset"}
              value={newDatasetName}
              maxLength={200}
              disabled={busy}
              onChange={(event) => setNewDatasetName(event.target.value)}
            />
          )}
        </div>
      </div>
      <div style={{ flexBasis: "100%" }}>
        <DomainChoice chosen={domains} onChange={setDomains} disabled={busy} />
      </div>
      {error && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {error}
        </span>
      )}
    </form>
  );
}
