// The analyst's map controls (P4, `02_GLASS_FRONTEND.md` §3.5): the basemap switch and the place
// search, drawn over the map by `MapView`. Both by keyboard alone (rule 13,
// `keyboard/map-view.spec.ts`'s `MAP_VIEW_ACTIONS`), in the dark, light and GOV.UK themes, colours
// from the tokens only.
//
// **The switch is a radio group**, not a native `<select>`: arrow keys move through a radio group and
// choose as they go on every platform, where a focused `<select>` opens its own menu on some, so a
// keyboard case could pass in one browser and the action be unreachable in another.
//
// **The search shows only the case's gazetteer** (ADR-147 Amendment 1): the places the gazetteer
// datasets the case reads hold. Nothing is looked up anywhere else, and the words say where the
// places come from, so an empty answer is not read as "this place does not exist".
import { useId, useState, type FormEvent } from "react";

import type { MapPlace, PublicMapProvider } from "../../../../packages/schemas/generated";
import { PlaceSearchFailed } from "./places";
import "./mapControls.css";

export interface BasemapSwitchProps {
  providers: readonly PublicMapProvider[];
  chosen: string;
  onChoose: (providerId: string) => void;
}

/** Each provider by its label, a hosted one named as hosted (`00_ARCHITECTURE.md` §1.2: the analyst
 * sees whenever a tier-3 layer is live). Drawn only when there is a choice to make. */
export function BasemapSwitch({ providers, chosen, onChoose }: BasemapSwitchProps) {
  const name = useId();
  if (providers.length < 2) return null;
  return (
    <fieldset className="map-controls__switch">
      <legend className="map-controls__legend">Basemap</legend>
      {providers.map((p) => (
        <label key={p.id} className="map-controls__choice">
          <input
            type="radio"
            name={name}
            value={p.id}
            checked={p.id === chosen}
            onChange={() => onChoose(p.id)}
          />
          {p.label}
          {p.client_scope !== "open" ? " (hosted)" : ""}
        </label>
      ))}
    </fieldset>
  );
}

export type SearchPlaces = (query: string) => Promise<{ places: MapPlace[]; more: boolean }>;

export interface PlaceSearchProps {
  search: SearchPlaces;
  onGo: (place: MapPlace) => void;
}

type Found =
  | { state: "idle" }
  | { state: "asking"; query: string }
  | { state: "found"; query: string; places: MapPlace[]; more: boolean }
  | { state: "failed"; words: string };

export function PlaceSearch({ search, onGo }: PlaceSearchProps) {
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Found>({ state: "idle" });
  const [shown, setShown] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const asked = query.trim();
    setShown(null);
    if (asked.length < 2) {
      setFound({ state: "failed", words: "Type at least two letters of the place's name." });
      return;
    }
    setFound({ state: "asking", query: asked });
    try {
      const answer = await search(asked);
      setFound({ state: "found", query: asked, places: answer.places, more: answer.more });
    } catch (err) {
      setFound({
        state: "failed",
        words:
          err instanceof PlaceSearchFailed ? err.message : "The place search failed. Try again.",
      });
    }
  }

  return (
    <div className="map-controls__search">
      <form role="search" aria-label="Find a place" onSubmit={(e) => void submit(e)}>
        <label htmlFor={inputId} className="map-controls__legend">
          Find a place
        </label>
        <div className="map-controls__row">
          <input
            id={inputId}
            className="input"
            type="search"
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit" className="btn">
            Find
          </button>
        </div>
      </form>
      <div role="status" className="map-controls__words">
        {found.state === "asking" && "Looking in this case's gazetteer…"}
        {found.state === "failed" && found.words}
        {found.state === "found" &&
          found.places.length === 0 &&
          (found.more
            ? // The store's first matches were all the case's own places (rule 2): not "none".
              `More places match “${found.query}” than were looked through; type more of the name.`
            : `No place called “${found.query}” is in the gazetteer this case reads.`)}
        {found.state === "found" &&
          found.places.length > 0 &&
          `${found.places.length} ${found.places.length === 1 ? "place" : "places"} found${
            found.more ? "; more match, so type more of the name" : ""
          }.`}
        {shown !== null && ` Showing ${shown}.`}
      </div>
      {found.state === "found" && found.places.length > 0 && (
        <ul className="map-controls__places" aria-label="Places found">
          {found.places.map((place) => (
            <li key={place.id}>
              <button
                type="button"
                className="btn btn--quiet"
                onClick={() => {
                  setShown(place.name);
                  onGo(place);
                }}
              >
                Go to {place.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="map-controls__note">Places come from the gazetteer datasets this case reads.</p>
    </div>
  );
}
