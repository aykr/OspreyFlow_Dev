// What the open case reads (ADR-099): every reader sees it; the case's Author changes it. Nothing
// else widens what a case reads, and a case always reads at least one dataset.
import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { type Dataset, caseDatasets, listCases, listDatasets, setCaseDatasets } from "./cases";
import { DatasetChoice } from "./DatasetChoice";

export interface CaseDatasetsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** What the case reads changed; the view is read again. */
  onChanged?: () => void;
}

export function CaseDatasets({
  apiBaseUrl,
  bearerToken,
  investigationId,
  onChanged,
}: CaseDatasetsProps) {
  // Offered to the case's Author only; the Conduit refuses anyone else whatever is shown here.
  const [canChange, setCanChange] = useState(false);
  const [reads, setReads] = useState<Dataset[] | null>(null);
  const [offered, setOffered] = useState<Dataset[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    caseDatasets(apiBaseUrl, bearerToken, investigationId)
      .then((found) => {
        if (cancelled) return;
        setReads(found);
        setChosen(found.map((d) => d.id));
      })
      .catch((err: unknown) => !cancelled && setProblem(err instanceof Error ? err.message : String(err)));
    listCases(apiBaseUrl, bearerToken)
      .then((cases) => {
        if (!cancelled) setCanChange(cases.some((c) => c.id === investigationId && c.level === "author"));
      })
      .catch(() => !cancelled && setCanChange(false));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  async function startChanging(): Promise<void> {
    setProblem(null);
    try {
      setOffered(await listDatasets(apiBaseUrl, bearerToken));
      setEditing(true);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    }
  }

  async function save(): Promise<void> {
    setBusy(true);
    setProblem(null);
    try {
      const saved = await setCaseDatasets(apiBaseUrl, bearerToken, investigationId, chosen);
      setReads(saved);
      setEditing(false);
      onChanged?.();
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Data this case reads" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="label" style={{ margin: 0 }}>
        Data this case reads
      </h3>
      {reads === null && !problem && <span className="label">Loading…</span>}
      {reads !== null && !editing && (
        <p style={{ margin: 0 }}>{reads.length > 0 ? reads.map((d) => d.name).join(", ") : "None"}</p>
      )}
      {editing && (
        <>
          <DatasetChoice
            datasets={offered}
            chosen={chosen}
            onChange={setChosen}
            legend="Read only these datasets"
            disabled={busy}
          />
          <span className="label">
            Search, expansion and the query builder in this case reach only these.
          </span>
          <span style={{ display: "flex", gap: "var(--sp-8)" }}>
            <Button variant="primary" disabled={busy || chosen.length === 0} onClick={() => void save()}>
              Save
            </Button>
            <Button
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setChosen((reads ?? []).map((d) => d.id));
              }}
            >
              Cancel
            </Button>
          </span>
        </>
      )}
      {reads !== null && !editing && canChange && (
        <span>
          <Button onClick={() => void startChanging()}>Change what this case reads</Button>
        </span>
      )}
      {problem && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {problem}
        </span>
      )}
    </section>
  );
}
