// The open case's own settings in the Cases drawer: "Data this case reads" (ADR-099) and "Domain
// models" (ADR-126). One read of the case's listing entry serves both, and it is read again after
// either is changed, so what the drawer shows afterwards is what the server now says. Who may change
// them is the entry's level and the person's rights; the Conduit refuses anyone else regardless.
import { useCallback, useEffect, useState } from "react";

import type { Rights } from "../rights/visibility";
import { CaseDatasets } from "./CaseDatasets";
import { CaseDomains } from "./CaseDomains";
import { type CaseListing, listCases } from "./cases";

export interface CaseSettingsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  rights?: Rights;
  /** Either setting changed, and the listing has been read again. */
  onChanged?: () => void;
}

export function CaseSettings({ apiBaseUrl, bearerToken, investigationId, rights = null, onChanged }: CaseSettingsProps) {
  // `undefined` while the listing is being read; `null` when the case is not in it.
  const [entry, setEntry] = useState<CaseListing | null | undefined>(undefined);
  const [problem, setProblem] = useState<string | null>(null);

  const read = useCallback(async () => {
    try {
      const cases = await listCases(apiBaseUrl, bearerToken);
      setEntry(cases.find((c) => c.id === investigationId) ?? null);
      setProblem(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    }
  }, [apiBaseUrl, bearerToken, investigationId]);

  useEffect(() => {
    void read();
  }, [read]);

  async function changed(): Promise<void> {
    await read();
    onChanged?.();
  }

  return (
    <>
      {problem && (
        <span role="alert" style={{ color: "var(--text-secondary)" }}>
          {problem}
        </span>
      )}
      {entry !== undefined && (
        <>
          <CaseDatasets
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            rights={rights}
            entry={entry}
            onChanged={() => void changed()}
          />
          <CaseDomains
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            rights={rights}
            entry={entry}
            onChanged={() => void changed()}
          />
        </>
      )}
    </>
  );
}
