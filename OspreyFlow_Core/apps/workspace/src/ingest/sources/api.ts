// Connections and registered sources (ADR-140 Amendment 4): the dataset's routes, which the Conduit
// scopes to the dataset only through a case of the person's that loads into it. A refusal comes back
// in the Conduit's own words.
import type {
  Connection,
  ConnectionInput,
  ConnectorRead,
  DatasetOwnListImportInput,
  DatasetSubscriptions,
  DeploymentList,
  DeploymentListInput,
  GovernanceEdited,
  ListImport,
  ListScheduleInput,
  OfferedList,
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

/** ADR-110 Amendment 13: pausing a source's refresh is not an edit (no new version, the owner kept). */
export const pauseRefresh = (api: SourcesApi, datasetId: string, sourceId: string, reason: string) =>
  call<SourceTable>(api, `${dataset(api, datasetId)}/sources/${encodeURIComponent(sourceId)}/refresh/pause`, "Pausing the refresh", {
    method: "POST",
    body: JSON.stringify({ reason: reason.trim() || null }),
  });

export const resumeRefresh = (api: SourcesApi, datasetId: string, sourceId: string) =>
  call<SourceTable>(api, `${dataset(api, datasetId)}/sources/${encodeURIComponent(sourceId)}/refresh/resume`, "Resuming the refresh", {
    method: "POST",
  });

// --- ADR-140 Amendment 13: connector sources, screening lists, subscriptions, a dataset's lists ---

/** *Refresh now* for a SQL, API or JSON source: read again into its file. */
export const readConnectorSource = (api: SourcesApi, datasetId: string, sourceId: string) =>
  call<ConnectorRead>(api, `${dataset(api, datasetId)}/sources/${encodeURIComponent(sourceId)}/read`, "Reading the source", {
    method: "POST",
  });

const studioLists = (api: SourcesApi) => `${api.apiBaseUrl}/v1/studio/screening-lists`;

/** The deployment-wide lists, for whoever may load screening lists; `null` for anyone else (403). */
export async function listDeploymentLists(api: SourcesApi): Promise<DeploymentList[] | null> {
  const response = await fetch(studioLists(api), { headers: { Authorization: `Bearer ${api.bearerToken}` } });
  if (response.status === 403) return null;
  if (!response.ok) throw new Error(`Reading the screening lists failed (${response.status}).`);
  return (await response.json()) as DeploymentList[];
}

export const addDeploymentList = (api: SourcesApi, body: DeploymentListInput) =>
  call<DeploymentList>(api, studioLists(api), "Adding the list", { method: "POST", body: JSON.stringify(body) });

export const refreshDeploymentList = (api: SourcesApi, listId: string) =>
  call<ListImport>(api, `${studioLists(api)}/${encodeURIComponent(listId)}/refresh`, "Refreshing the list", { method: "POST" });

export const setDeploymentListSchedule = (api: SourcesApi, listId: string, body: ListScheduleInput) =>
  call<DeploymentList>(api, `${studioLists(api)}/${encodeURIComponent(listId)}/schedule`, "Setting the schedule", {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const listSubscriptions = (api: SourcesApi, datasetId: string) =>
  call<DatasetSubscriptions>(api, `${dataset(api, datasetId)}/screening-subscriptions`, "Reading the subscriptions");

export const setSubscribed = (api: SourcesApi, datasetId: string, listId: string, subscribed: boolean) =>
  call<DatasetSubscriptions>(
    api,
    `${dataset(api, datasetId)}/screening-subscriptions/${encodeURIComponent(listId)}`,
    subscribed ? "Subscribing" : "Unsubscribing",
    { method: subscribed ? "PUT" : "DELETE" },
  );

export const offeredLists = (api: SourcesApi, datasetId: string) =>
  call<OfferedList[]>(api, `${dataset(api, datasetId)}/reference-lists/offered`, "Reading the lists");

export const importOwnList = (api: SourcesApi, datasetId: string, listId: string, body: DatasetOwnListImportInput) =>
  call<ListImport>(api, `${dataset(api, datasetId)}/reference-lists/${encodeURIComponent(listId)}/import`, "Importing the list", {
    method: "POST",
    body: JSON.stringify(body),
  });
