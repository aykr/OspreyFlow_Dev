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

/** The places a person's rights open, in the switcher's order. While the rights are not yet known,
 * or could not be read (`null`), none: a place is offered only on a right the Conduit has named. */
export function placesFor(rights: ReadonlySet<string> | null): PlaceId[] {
  if (rights === null) return [];
  return PLACES.filter((place) => place.rights.some((right) => rights.has(right))).map((place) => place.id);
}

export const PLACE_KEY: Record<PlaceId, string> = Object.fromEntries(PLACES.map((p) => [p.id, p.key.toUpperCase()])) as Record<
  PlaceId,
  string
>;
