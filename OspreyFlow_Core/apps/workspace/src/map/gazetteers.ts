// The case's gazetteers beside the map's place search (P6; ADR-147 Amendment 2, the owner's ruling
// 6): `GET /v1/investigations/{id}/map/gazetteers` lists the gazetteers of the case's dataset's
// unit, each added or not, and `PUT`/`DELETE /v1/datasets/{dataset}/gazetteers/{gazetteer}` add
// and remove one. Adding copies its places into the case's own dataset; removing deletes nothing
// and takes them out of the place search. Names only, never a count of places.
import type { CaseGazetteer, CaseGazetteers } from "../../../../packages/schemas/generated";
import type { Dataset } from "../investigation/cases";

/** Refused or unreachable, in words the map shows; never the Conduit's own error text. */
export class GazetteersFailed extends Error {}

/** What the panel shows. The Conduit's list is empty for three reasons it does not tell apart, so
 * the datasets the case reads tell them apart here: none; a composite or more than one (a
 * gazetteer is added to the one source dataset a case reads); or none built for its unit. */
export type GazetteerPanelState =
  | { state: "ready"; datasetId: string; gazetteers: CaseGazetteer[] }
  | { state: "reads_nothing" }
  | { state: "not_one_source" }
  | { state: "none_built" };

async function ask(
  url: string,
  bearerToken: string,
  method: "GET" | "PUT" | "DELETE",
  fetchImpl: typeof fetch,
): Promise<Response> {
  try {
    return await fetchImpl(url, { method, headers: { Authorization: `Bearer ${bearerToken}` } });
  } catch {
    throw new GazetteersFailed("The gazetteers could not reach the Conduit. Try again.");
  }
}

export async function caseGazetteers(
  baseUrl: string,
  bearerToken: string,
  investigationId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<GazetteerPanelState> {
  const theCase = `${baseUrl}/v1/investigations/${encodeURIComponent(investigationId)}`;
  const [listed, read] = await Promise.all([
    ask(`${theCase}/map/gazetteers`, bearerToken, "GET", fetchImpl),
    ask(`${theCase}/datasets`, bearerToken, "GET", fetchImpl),
  ]);
  for (const response of [listed, read]) {
    if (response.status === 403) throw new GazetteersFailed("You may not see this case's gazetteers.");
    if (!response.ok) {
      throw new GazetteersFailed(`The gazetteers could not be read (HTTP ${response.status}). Try again.`);
    }
  }
  const { gazetteers } = (await listed.json()) as CaseGazetteers;
  const datasets = (await read.json()) as Dataset[];
  if (datasets.length === 0) return { state: "reads_nothing" };
  const [only] = datasets;
  // An older Conduit sends no kind: a source, as every dataset was before composites.
  if (datasets.length > 1 || only === undefined || (only.kind ?? "source") !== "source") {
    return { state: "not_one_source" };
  }
  if (gazetteers.length === 0) return { state: "none_built" };
  return { state: "ready", datasetId: only.id, gazetteers };
}

async function change(
  method: "PUT" | "DELETE",
  baseUrl: string,
  bearerToken: string,
  datasetId: string,
  gazetteerId: string,
  fetchImpl: typeof fetch,
): Promise<CaseGazetteers> {
  const response = await ask(
    `${baseUrl}/v1/datasets/${encodeURIComponent(datasetId)}/gazetteers/${encodeURIComponent(gazetteerId)}`,
    bearerToken,
    method,
    fetchImpl,
  );
  if (response.status === 403) {
    throw new GazetteersFailed(
      "You may not change this dataset's gazetteers: it needs the right to run pipelines.",
    );
  }
  if (response.status === 404) {
    throw new GazetteersFailed("There is no gazetteer of that name for this case's dataset's unit.");
  }
  if (response.status === 409) {
    throw new GazetteersFailed("This case's dataset takes no gazetteer: it is a composite or a drawing.");
  }
  if (!response.ok) {
    throw new GazetteersFailed(`The gazetteer could not be changed (HTTP ${response.status}). Try again.`);
  }
  return (await response.json()) as CaseGazetteers;
}

export function addGazetteer(
  baseUrl: string,
  bearerToken: string,
  datasetId: string,
  gazetteerId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<CaseGazetteers> {
  return change("PUT", baseUrl, bearerToken, datasetId, gazetteerId, fetchImpl);
}

export function removeGazetteer(
  baseUrl: string,
  bearerToken: string,
  datasetId: string,
  gazetteerId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<CaseGazetteers> {
  return change("DELETE", baseUrl, bearerToken, datasetId, gazetteerId, fetchImpl);
}
