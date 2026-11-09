// The map's place search (`02_GLASS_FRONTEND.md` §3.5's gazetteer search, ADR-147 Amendment 1):
// `POST /v1/investigations/{id}/map/places`, the loaded gazetteer's places in the case's datasets.
// Never a hosted geocoder: the Conduit calls none for this, and the Glass calls nothing but it.
import type {
  PlaceSearchResponse,
} from "../../../../packages/schemas/generated";

/** Refused or unreachable, in words the map shows; never the Conduit's own error text. */
export class PlaceSearchFailed extends Error {}

export async function searchPlaces(
  baseUrl: string,
  bearerToken: string,
  investigationId: string,
  query: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PlaceSearchResponse> {
  let response: Response;
  try {
    response = await fetchImpl(
      `${baseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/map/places`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      },
    );
  } catch {
    throw new PlaceSearchFailed("The place search could not reach the Conduit. Try again.");
  }
  if (response.status === 403) {
    throw new PlaceSearchFailed("You may not search this case's places.");
  }
  if (!response.ok) {
    throw new PlaceSearchFailed(`The place search failed (HTTP ${response.status}). Try again.`);
  }
  return (await response.json()) as PlaceSearchResponse;
}
