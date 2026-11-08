// Registering a source, once (ADR-140 decision 7, Amendment 4): 1 Connection, 2 File, 3 Governance and
// refresh, then Register, after which its profile is shown. Governance comes before the profile
// because the profiler masks sample values by the source's marking and refuses a source with none.
// Back on every step; nothing is written until Register. On a SQL, API or JSON connection (ADR-140
// Amendment 13) the second step is the source's read instead of a file: Register reads it once, into its
// own file in the dataset's folder, and registers it only if that read succeeds.
import { useEffect, useState } from "react";

import type { Connection, RegisterSourceInput, SourceTable } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import type { HandlingScheme, IngestSourceFile } from "../api";
import { listConnections, listDatasetFiles, registerSource, type SourcesApi } from "./api";
import { EMPTY_GOVERNANCE, type Governance, GovernanceFields, handlingOf, missing } from "./GovernanceFields";

const STEPS = ["Connection", "File", "Governance and refresh"] as const;
const READ_STEPS = ["Connection", "What to read", "Governance and refresh"] as const;

/** A source's own name for its file: lower case, digits, '-' and '_' (the Conduit's rule). */
export function fileNameOf(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^[_-]+|[_-]+$/g, "")
    .slice(0, 63);
}

type ReadFields = { table: string; columns: string; path: string; recordsAt: string; pattern: string };
const EMPTY_READ: ReadFields = { table: "", columns: "", path: "", recordsAt: "", pattern: "" };

/** The source's read, in the shape the Conduit takes; `null` while a field it needs is missing. */
export function readOf(kind: string, f: ReadFields): RegisterSourceInput["read"] | null {
  const recordsAt = f.recordsAt.trim() || null;
  if (kind === "sql") {
    if (!f.table.trim()) return null;
    const columns = f.columns.split(",").map((c) => c.trim()).filter(Boolean);
    return { kind: "sql", table: f.table.trim(), columns };
  }
  if (kind === "api") return f.path.trim() ? { kind: "api", path: f.path.trim(), records_at: recordsAt } : null;
  if (kind === "json") return f.pattern.trim() ? { kind: "json", pattern: f.pattern.trim(), records_at: recordsAt } : null;
  return null;
}

export interface RegisterSourceWizardProps {
  api: SourcesApi;
  datasetId: string;
  scheme: HandlingScheme | null;
  /** The files already registered for the dataset, by location: not offered again. */
  registered: readonly string[];
  onRegistered: (source: SourceTable) => void;
  onCancel: () => void;
}

export function RegisterSourceWizard({ api, datasetId, scheme, registered, onRegistered, onCancel }: RegisterSourceWizardProps) {
  const [step, setStep] = useState(0);
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [files, setFiles] = useState<IngestSourceFile[] | null>(null);
  const [connectionId, setConnectionId] = useState("files");
  const [location, setLocation] = useState("");
  const [name, setName] = useState("");
  const [governance, setGovernance] = useState<Governance>(EMPTY_GOVERNANCE);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [read, setRead] = useState<ReadFields>(EMPTY_READ);
  const kind = connections?.find((c) => c.id === connectionId)?.kind ?? "files";
  const throughConnection = kind !== "files";
  const steps = throughConnection ? READ_STEPS : STEPS;
  const sourceRead = throughConnection ? readOf(kind, read) : null;

  useEffect(() => {
    listConnections(api).then(setConnections).catch((e: Error) => setProblem(e.message));
    listDatasetFiles(api, datasetId)
      .then((listing) => setFiles(listing.files.filter((f) => !registered.includes(f.source_location))))
      .catch((e: Error) => setProblem(e.message));
  }, [api, datasetId, registered]);

  const gaps = missing(governance);
  const ready = [
    connectionId !== "",
    throughConnection ? name.trim() !== "" && fileNameOf(name) !== "" && sourceRead !== null : location !== "" && name.trim() !== "",
    gaps.length === 0,
  ];

  async function register() {
    setBusy(true);
    setProblem(null);
    try {
      const made = await registerSource(api, datasetId, {
        connection_id: connectionId,
        name: name.trim(),
        location: throughConnection ? fileNameOf(name) : location,
        read: sourceRead,
        connector_profile: "generic-csv",
        handling: handlingOf(governance),
        legal_basis: governance.legalBasis.trim(),
        refresh: governance.refresh,
      });
      onRegistered(made);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "The source could not be registered.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Register a source" style={{ display: "grid", gap: "var(--sp-12)" }}>
      <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>Register a source</h2>
      <ol aria-label="Steps" style={{ display: "flex", gap: "var(--sp-16)", margin: 0, paddingLeft: "var(--sp-16)" }}>
        {steps.map((label, i) => (
          <li key={label} aria-current={i === step ? "step" : undefined} style={{ fontWeight: i === step ? 600 : 400 }}>
            {label}
          </li>
        ))}
      </ol>
      {step === 0 && (
        <label style={{ display: "grid", gap: "var(--sp-2)", maxWidth: 520 }}>
          <span className="label">Connection</span>
          <Select value={connectionId} onChange={(e) => setConnectionId(e.target.value)}>
            {(connections ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </label>
      )}
      {step === 1 && throughConnection && (
        <div style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}>
          <label style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span className="label">Source name</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          {name.trim() && (
            <p className="label" style={{ margin: 0 }}>{`Each read lands as ${fileNameOf(name) || "…"}.csv in the dataset's folder.`}</p>
          )}
          {kind === "sql" && (
            <>
              <label style={{ display: "grid", gap: "var(--sp-2)" }}>
                <span className="label">Table or view (schema.name)</span>
                <Input value={read.table} onChange={(e) => setRead({ ...read, table: e.target.value })} />
              </label>
              <label style={{ display: "grid", gap: "var(--sp-2)" }}>
                <span className="label">Columns, separated by commas (all of them when empty)</span>
                <Input value={read.columns} onChange={(e) => setRead({ ...read, columns: e.target.value })} />
              </label>
            </>
          )}
          {kind === "api" && (
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">Path under the connection&apos;s address</span>
              <Input value={read.path} onChange={(e) => setRead({ ...read, path: e.target.value })} placeholder="/v1/records" />
            </label>
          )}
          {kind === "json" && (
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">File names to read (* and ? match)</span>
              <Input value={read.pattern} onChange={(e) => setRead({ ...read, pattern: e.target.value })} placeholder="bookings-*.json" />
            </label>
          )}
          {(kind === "api" || kind === "json") && (
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">Where the records are (dotted names; the top level when empty)</span>
              <Input value={read.recordsAt} onChange={(e) => setRead({ ...read, recordsAt: e.target.value })} placeholder="data.items" />
            </label>
          )}
        </div>
      )}
      {step === 1 && !throughConnection && (
        <div style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}>
          <label style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span className="label">File</span>
            <Select
              value={location}
              onChange={(e) => {
                setLocation(e.target.value);
                const file = (files ?? []).find((f) => f.source_location === e.target.value);
                if (file && !name.trim()) setName(file.name);
              }}
            >
              <option value="">Choose a file</option>
              {(files ?? []).map((f) => (
                <option key={f.source_location} value={f.source_location}>
                  {f.name}
                </option>
              ))}
            </Select>
          </label>
          {files?.length === 0 && (
            <p className="label" style={{ margin: 0 }}>
              Every file of this dataset is registered already, or there are none in its folder yet.
            </p>
          )}
          <label style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span className="label">Source name</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        </div>
      )}
      {step === 2 && (
        <>
          <GovernanceFields scheme={scheme} value={governance} onChange={setGovernance} />
          {gaps.length > 0 && <p className="label" style={{ margin: 0 }}>{`Still to give: ${gaps.join(", ")}.`}</p>}
        </>
      )}
      {problem && <p role="alert">{problem}</p>}
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        {step > 0 ? <Button onClick={() => setStep(step - 1)}>Back</Button> : <Button onClick={onCancel}>Cancel</Button>}
        {step < steps.length - 1 ? (
          <Button variant="primary" disabled={!ready[step]} onClick={() => setStep(step + 1)}>
            Next
          </Button>
        ) : (
          <Button variant="primary" disabled={!ready.every(Boolean) || busy} onClick={() => void register()}>
            {busy ? "Registering…" : "Register"}
          </Button>
        )}
      </div>
    </section>
  );
}
