// The three places (ADR-145 decisions 1 and N6): the Glass, the Ingest Studio and Admin, from the one
// table the Conduit's routes are checked against (`places.json`, read by
// `OspreyFlow_Build/tests/services/api/test_place_routes.py`). A place is offered to whoever holds one
// of its rights. Hiding is never the control: each hidden place's routes refuse the person anyway.
import table from "./places.json";

export type PlaceId = "glass" | "ingest" | "admin";

export interface Place {
  id: PlaceId;
  /** As the switcher, Home and the banner name it. */
  name: string;
  /** Home's key for it (G, I, A). */
  key: string;
  /** What the place holds, in order (ADR-145 decision 1). */
  sections: string[];
  rights: string[];
}

export const PLACES: readonly Place[] = table.places as Place[];

export const PLACE_NAME: Record<PlaceId, string> = Object.fromEntries(PLACES.map((p) => [p.id, p.name])) as Record<
  PlaceId,
  string
>;

/** The places a person's rights open, in the switcher's order. While the rights are not yet known
 * (`null`), the Glass and the Studio, as the Glass always showed; Admin only once a right is known. */
export function placesFor(rights: ReadonlySet<string> | null): PlaceId[] {
  return PLACES.filter((place) =>
    rights === null ? place.id !== "admin" : place.rights.some((right) => rights.has(right)),
  ).map((place) => place.id);
}
