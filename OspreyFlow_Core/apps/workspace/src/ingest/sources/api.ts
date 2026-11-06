// Connections and registered sources (ADR-140 Amendment 4): the dataset's routes, which the Conduit
// scopes to the dataset only through a case of the person's that loads into it. A refusal comes back
// in the Conduit's own words.
import type {
  Connection,
  ConnectionInput,
  GovernanceEdited,
  RegisterSourceInput,
  SourceGovernanceInput,
  SourceLineage,
  SourceProfile,
  SourceTable,
} from "../../../../../packages/schemas/generated";
import type { IngestSourceListing } from "../api";

export interface SourcesApi {
  apiBaseUrl: string;
  bearerToken: string;
}

function dataset(api: SourcesApi, datasetId: string): string {
  return `${api.apiBaseUrl}/v1/datasets/${encodeURIComponent(datasetId)}`;
}

async function call<T>(api: SourcesApi, url: string, what: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${api.bearerToken}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    let words = `${what} failed (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      const detail = body.detail as { detail?: string } | string | undefined;
      if (typeof detail === "string" && detail !== "not_found") words = detail;
      else if (detail && typeof detail === "object" && typeof detail.detail === "string") words = detail.detail;
    } catch {
      // Not a JSON body: the status says it.
    }
    throw new Error(words);
  }
  return (await response.json()) as T;
}

export const listConnections = (api: SourcesApi) =>
  call<Connection[]>(api, `${api.apiBaseUrl}/v1/ingest/connections`, "Reading the connections");

export const listAdminConnections = (api: SourcesApi) =>
  call<Connection[]>(api, `${api.apiBaseUrl}/v1/admin/connections`, "Reading the connections");

export const addConnection = (api: SourcesApi, body: ConnectionInput) =>
  call<Connection>(api, `${api.apiBaseUrl}/v1/admin/connections`, "Naming the connection", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const listDatasetFiles = (api: SourcesApi, datasetId: string) =>
  call<IngestSourceListing>(api, `${dataset(api, datasetId)}/source-files`, "Reading the dataset's files");

export const listSources = (api: SourcesApi, datasetId: string) =>
  call<SourceTable[]>(api, `${dataset(api, datasetId)}/sources`, "Reading the sources");

export const registerSource = (api: SourcesApi, datasetId: string, body: RegisterSourceInput) =>
  call<SourceTable>(api, `${dataset(api, datasetId)}/sources`, "Registering the source", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const sourceProfile = (api: SourcesApi, datasetId: string, sourceId: string) =>
  call<SourceProfile>(api, `${dataset(api, datasetId)}/sources/${encodeURIComponent(sourceId)}/profile`, "Profiling the source");

export const sourceLineage = (api: SourcesApi, datasetId: string, sourceId: string) =>
  call<SourceLineage[]>(api, `${dataset(api, datasetId)}/sources/${encodeURIComponent(sourceId)}/lineage`, "Reading the lineage");

export const editGovernance = (api: SourcesApi, datasetId: string, sourceId: string, body: SourceGovernanceInput) =>
  call<GovernanceEdited>(api, `${dataset(api, datasetId)}/sources/${encodeURIComponent(sourceId)}/governance`, "Editing the governance", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
