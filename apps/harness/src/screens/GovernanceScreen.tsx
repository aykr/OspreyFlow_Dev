import { useEffect, useState } from "react";

import {
  addRealDataException,
  ApiError,
  getRealDataExceptions,
  removeRealDataException,
} from "../api/client";
import type { NewRealDataException, OspreyConfig, RealDataException } from "../api/types";

//: `05_DEPLOYMENT.md` §2.1's own "Ships with a UK law-enforcement scheme, a US
//: criminal-intelligence scheme" — `packages/ontology/handling.py`'s own two loaders,
//: `load_uk_le_scheme`/`load_us_criminal_intelligence_scheme`, are what these two values select
//: between; there is no third scheme shipped yet.
const HANDLING_SCHEMES = ["uk-law-enforcement", "us-criminal-intelligence"] as const;

//: `scripts/real_data_exceptions.py`'s own `APPROVED_USES`.
const APPROVED_USES = ["local_development", "scale_testing", "owner_run_demonstration"] as const;

function ExceptionsPanel() {
  const [entries, setEntries] = useState<RealDataException[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dataset, setDataset] = useState("");
  const [uses, setUses] = useState<Set<string>>(new Set());
  const [addedBy, setAddedBy] = useState("");
  const [device, setDevice] = useState("");
  const [justification, setJustification] = useState("");
  const [decisionRecord, setDecisionRecord] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function refresh() {
    getRealDataExceptions()
      .then((result) => {
        setEntries(result.exceptions);
        setLoadError(null);
      })
      .catch((exc) => {
        // `CLAUDE.md` rule 2 — an existing local entry that fails a required-field check (most
        // often: predates `decision_record`) is shown verbatim, never silently as an empty list.
        setEntries(null);
        setLoadError(exc instanceof ApiError ? exc.body : String(exc));
      });
  }

  useEffect(refresh, []);

  function toggleUse(use: string) {
    setUses((previous) => {
      const next = new Set(previous);
      if (next.has(use)) next.delete(use);
      else next.add(use);
      return next;
    });
  }

  async function handleAdd() {
    setSaving(true);
    setAddError(null);
    try {
      const entry: NewRealDataException = {
        dataset,
        approved_uses: [...uses],
        added_by: addedBy,
        device,
        justification,
        decision_record: decisionRecord,
      };
      await addRealDataException(entry);
      setDataset("");
      setUses(new Set());
      setAddedBy("");
      setDevice("");
      setJustification("");
      setDecisionRecord("");
      refresh();
    } catch (exc) {
      setAddError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove(dataset: string) {
    await removeRealDataException(dataset);
    refresh();
  }

  return (
    <section aria-labelledby="real-data-exceptions-heading">
      <h3 id="real-data-exceptions-heading">Real-data exceptions</h3>
      <p>
        Local, never-committed admissions only (<code>CLAUDE.md</code> rule 9 / ADR-035 §C3) — this
        panel reads and writes the gitignored file at the path above, never a fixture and never CI.
      </p>

      {loadError && <p role="alert">{loadError}</p>}
      {entries && entries.length === 0 && !loadError && <p>No real-data exceptions configured.</p>}
      {entries && entries.length > 0 && (
        <ul>
          {entries.map((entry) => (
            <li key={entry.dataset}>
              <strong>{entry.dataset}</strong> — {entry.approved_uses.join(", ")}, added{" "}
              {entry.added_date} by {entry.added_by} for {entry.device} ({entry.decision_record})
              <button type="button" className="btn" onClick={() => handleRemove(entry.dataset)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <h4>Add an exception</h4>
      <label htmlFor="rde-dataset">Dataset name</label>
      <input
        id="rde-dataset"
        className="input"
        value={dataset}
        onChange={(event) => setDataset(event.target.value)}
      />

      <fieldset>
        <legend>Approved uses</legend>
        {APPROVED_USES.map((use) => (
          <label key={use}>
            <input type="checkbox" checked={uses.has(use)} onChange={() => toggleUse(use)} /> {use}
          </label>
        ))}
      </fieldset>

      <label htmlFor="rde-added-by">Added by</label>
      <input
        id="rde-added-by"
        className="input"
        value={addedBy}
        onChange={(event) => setAddedBy(event.target.value)}
      />

      <label htmlFor="rde-device">Device</label>
      <input
        id="rde-device"
        className="input"
        value={device}
        onChange={(event) => setDevice(event.target.value)}
      />

      <label htmlFor="rde-justification">Justification</label>
      <input
        id="rde-justification"
        className="input"
        value={justification}
        onChange={(event) => setJustification(event.target.value)}
      />

      <label htmlFor="rde-decision-record">Decision record (e.g. ADR-035 §C3)</label>
      <input
        id="rde-decision-record"
        className="input"
        value={decisionRecord}
        onChange={(event) => setDecisionRecord(event.target.value)}
      />

      {addError && <p role="alert">{addError}</p>}
      <button type="button" className="btn btn--primary" onClick={handleAdd} disabled={saving}>
        Add exception
      </button>
    </section>
  );
}

export function GovernanceScreen({
  config,
  onSave,
}: {
  config: OspreyConfig;
  onSave: (patch: Partial<OspreyConfig>) => Promise<void>;
}) {
  const [identityProvider, setIdentityProvider] = useState(
    config.governance?.identity_provider ?? "keycloak",
  );
  const [handlingScheme, setHandlingScheme] = useState(
    config.governance?.handling_scheme ?? "uk-law-enforcement",
  );
  const [ontology, setOntology] = useState(config.governance?.ontology ?? "default");
  const [exceptionsPath, setExceptionsPath] = useState(
    config.governance?.real_data_exceptions ?? "config/real_data_exceptions.yaml",
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        governance: {
          identity_provider: identityProvider,
          handling_scheme: handlingScheme,
          ontology,
          real_data_exceptions: exceptionsPath,
        },
      });
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="governance-heading">
      <h2 id="governance-heading">Governance</h2>

      <label htmlFor="identity-provider">Identity provider</label>
      <input
        id="identity-provider"
        className="input"
        value={identityProvider}
        onChange={(event) => setIdentityProvider(event.target.value)}
      />

      <label htmlFor="handling-scheme">Handling scheme</label>
      <select
        id="handling-scheme"
        className="select"
        value={handlingScheme}
        onChange={(event) => setHandlingScheme(event.target.value)}
      >
        {HANDLING_SCHEMES.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>

      <label htmlFor="ontology">Ontology</label>
      <input
        id="ontology"
        className="input"
        value={ontology}
        onChange={(event) => setOntology(event.target.value)}
      />

      <label htmlFor="real-data-exceptions-path">Real-data exceptions file path</label>
      <input
        id="real-data-exceptions-path"
        className="input"
        value={exceptionsPath}
        onChange={(event) => setExceptionsPath(event.target.value)}
      />

      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save governance
      </button>

      <ExceptionsPanel />
    </section>
  );
}
