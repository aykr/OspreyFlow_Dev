// The dataset's registered sources for the readiness strip (ADR-140 Amendment 6), read through the
// dataset's own route, which the Conduit scopes to a dataset one of the person's cases loads into.
// A failed read is said, never shown as no sources.
import { useEffect, useMemo, useState } from "react";

import type { SourceTable } from "../../../../../packages/schemas/generated";
import { listSources } from "../sources/api";

export type RegisteredSources = SourceTable[] | null | "unreadable";

/** `ready`: the person's cases have been read, so `datasetId` is settled (`null` then means the
 * case loads into no dataset, which has no sources). `generation` reads them again. */
export function useRegisteredSources(
  apiBaseUrl: string,
  bearerToken: string,
  datasetId: string | null,
  ready: boolean,
  generation: number,
): RegisteredSources {
  const api = useMemo(() => ({ apiBaseUrl, bearerToken }), [apiBaseUrl, bearerToken]);
  const [sources, setSources] = useState<RegisteredSources>(null);

  useEffect(() => {
    if (!ready) return;
    if (!datasetId) {
      setSources([]);
      return;
    }
    let cancelled = false;
    listSources(api, datasetId)
      .then((found) => !cancelled && setSources(found))
      .catch(() => !cancelled && setSources("unreadable"));
    return () => {
      cancelled = true;
    };
  }, [api, datasetId, ready, generation]);

  return sources;
}
