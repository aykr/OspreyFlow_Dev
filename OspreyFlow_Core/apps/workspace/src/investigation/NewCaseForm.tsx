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
}

export function NewCaseForm({ apiBaseUrl, bearerToken, inputLabel, onCreated }: NewCaseFormProps) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // ADR-099 (presentation: Amendment 8, the owner's 9 October 2026 choice): what the case can
  // see is a first-class choice, "start empty" the default; the datasets show only when asked
  // for, and leaving the "existing" choice forgets what was ticked there.
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [mode, setMode] = useState<"empty" | "existing">("empty");
  const [chosen, setChosen] = useState<string[]>([]);
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
      const created = await createCase(apiBaseUrl, bearerToken, name, mode === "existing" ? chosen : [], domains);
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
      <div style={{ flexBasis: "100%", display: "grid", gap: "var(--sp-8)" }}>
        <span className="label">What can this case see?</span>
        <RadioGroup
          name="new-case-data"
          aria-label="What can this case see?"
          value={mode}
          onChange={(value) => {
            setMode(value as "empty" | "existing");
            if (value === "empty") setChosen([]);
          }}
          options={[
            { value: "empty", label: "Start empty — it holds only the data you load into it" },
            { value: "existing", label: "Read existing data…" },
          ]}
        />
        {mode === "existing" && (
          <div style={{ display: "grid", gap: "var(--sp-4)", paddingLeft: "var(--sp-24)" }}>
            <DatasetChoice
              datasets={datasets}
              chosen={chosen}
              onChange={setChosen}
              legend="A case reads only the data given here; its Author can change this later."
              disabled={busy}
            />
          </div>
        )}
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
