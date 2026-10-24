// The open case's domain models (ADR-126 decision 1), beside "Data this case reads": every reader
// sees which packs the case carries, which says what kind of case it is and never what it holds;
// the case's Author changes them. Nothing else does, and the Conduit refuses anyone else whatever
// is shown here.
import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { canChangeCase, type Rights } from "../rights/visibility";
import { type CaseListing, type DomainPack, changeCaseDomains, domainLabels, listCases } from "./cases";
import { DomainChoice } from "./DomainChoice";

export interface CaseDomainsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The packs changed; the view is read again. */
  onChanged?: () => void;
  /** The person's rights (`GET /v1/me/rights`); the change is offered only with `share_case`. */
  rights?: Rights;
  /** The case's entry in the listing, read once by the caller for both settings (`CaseSettings`).
   * `null` is "no such entry"; left out, this reads the listing itself. */
  entry?: CaseListing | null;
}

export function CaseDomains({ apiBaseUrl, bearerToken, investigationId, onChanged, rights = null, entry }: CaseDomainsProps) {
  const [canChange, setCanChange] = useState(false);
  const [held, setHeld] = useState<DomainPack[] | null>(null);
  const [chosen, setChosen] = useState<DomainPack[]>([]);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  // Given its entry, it shows what that says and reads nothing; otherwise it reads the listing.
  useEffect(() => {
    if (entry === undefined) return;
    setHeld(entry?.domains ?? []);
    setChosen(entry?.domains ?? []);
    setCanChange(canChangeCase(rights, entry?.level));
  }, [entry, rights]);

  useEffect(() => {
    if (entry !== undefined) return;
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((cases) => {
        if (cancelled) return;
        const found = cases.find((c) => c.id === investigationId);
        setHeld(found?.domains ?? []);
        setChosen(found?.domains ?? []);
        setCanChange(canChangeCase(rights, found?.level));
      })
      .catch((err: unknown) => !cancelled && setProblem(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, entry, rights]);

  async function save(): Promise<void> {
    setBusy(true);
    setProblem(null);
    try {
      const saved = await changeCaseDomains(apiBaseUrl, bearerToken, investigationId, chosen);
      setHeld(saved);
      setChosen(saved);
      setEditing(false);
      onChanged?.();
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Domain models" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="label" style={{ margin: 0 }}>
        Domain models
      </h3>
      {held === null && !problem && <span className="label">Loading…</span>}
      {held !== null && !editing && <p style={{ margin: 0 }}>{domainLabels(held)}</p>}
      {editing && (
        <>
          <DomainChoice chosen={chosen} onChange={setChosen} legend="Choose the domain models" disabled={busy} />
          <span className="label">
            They choose which figures the Reports view draws and which link types Trends offers.
          </span>
          <span style={{ display: "flex", gap: "var(--sp-8)" }}>
            <Button variant="primary" disabled={busy} onClick={() => void save()}>
              Save
            </Button>
            <Button
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setChosen(held ?? []);
              }}
            >
              Cancel
            </Button>
          </span>
        </>
      )}
      {held !== null && !editing && canChange && (
        <span>
          <Button onClick={() => setEditing(true)}>Change domain models</Button>
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
