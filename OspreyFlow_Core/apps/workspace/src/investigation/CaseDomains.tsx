// The open case's domain models (ADR-126), beside "Data this case reads": every reader sees which
// packs the case carries, which says what kind of case it is and never what it holds. Read-only
// (ADR-126 Amendment 2): the packs come from the case's dataset's domain model, changed only on the
// Ingest Studio's Model tab, where they change for every case reading the dataset. The Conduit
// refuses a change of packs through the case (409 `packs_from_the_model`).
import { useEffect, useState } from "react";

import { type CaseListing, type DomainPack, domainLabels, listCases } from "./cases";

export interface CaseDomainsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The case's entry in the listing, read once by the caller for both settings (`CaseSettings`).
   * `null` is "no such entry"; left out, this reads the listing itself. */
  entry?: CaseListing | null;
}

/** The one sentence that says where the packs come from, in the "domain model" wording. */
export const FROM_THE_DATASET = "These come from the dataset's domain model, and change there, in the Ingest Studio.";

export function CaseDomains({ apiBaseUrl, bearerToken, investigationId, entry }: CaseDomainsProps) {
  const [held, setHeld] = useState<DomainPack[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  // Given its entry, it shows what that says and reads nothing; otherwise it reads the listing.
  useEffect(() => {
    if (entry === undefined) return;
    setHeld(entry?.domains ?? []);
  }, [entry]);

  useEffect(() => {
    if (entry !== undefined) return;
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((cases) => {
        if (cancelled) return;
        setHeld(cases.find((c) => c.id === investigationId)?.domains ?? []);
      })
      .catch((err: unknown) => !cancelled && setProblem(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, entry]);

  return (
    <section aria-label="Domain models" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="label" style={{ margin: 0 }}>
        Domain models
      </h3>
      {held === null && !problem && <span className="label">Loading…</span>}
      {held !== null && (
        <>
          <p style={{ margin: 0 }}>{domainLabels(held)}</p>
          <span className="label">{FROM_THE_DATASET}</span>
        </>
      )}
      {problem && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {problem}
        </span>
      )}
    </section>
  );
}
