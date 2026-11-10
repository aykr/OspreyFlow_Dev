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
//
// **The case's gazetteers sit beside the search** (P6; ADR-147 Amendment 2, the owner's ruling 6):
// each gazetteer of the case's dataset's unit by name, added or not, with Add and Remove for a
// person holding the right to run pipelines (the Conduit refuses anyone else all the same). Names
// only, never a count of places; a removal says the Conduit's fixed words.
import { useEffect, useId, useState, type FormEvent } from "react";

import type {
  CaseGazetteer,
  CaseGazetteers,
  MapPlace,
  PublicMapProvider,
} from "../../../../packages/schemas/generated";
import { GazetteersFailed, type GazetteerPanelState } from "./gazetteers";
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

export interface GazetteerControls {
  /** `gazetteers.ts`'s `caseGazetteers`, bound to the case. */
  load: () => Promise<GazetteerPanelState>;
  add: (datasetId: string, gazetteerId: string) => Promise<CaseGazetteers>;
  remove: (datasetId: string, gazetteerId: string) => Promise<CaseGazetteers>;
  /** The person holds `run_pipelines`; without it no change is offered. */
  mayChange: boolean;
}

export interface CaseGazetteerPanelProps extends GazetteerControls {
  /** A gazetteer was added or removed: the place search offers other places now. */
  onChanged: () => void;
}

/** Why the panel lists nothing, in words naming no dataset (the orchestrator's ruling on P6). */
const EMPTY_WORDS: Record<Exclude<GazetteerPanelState["state"], "ready">, string> = {
  reads_nothing: "This case reads no dataset yet, so it has no gazetteer to add.",
  not_one_source:
    "A gazetteer is added to the one dataset a case reads, and this case reads a composite or " +
    "more than one, so none can be added here.",
  none_built:
    "No gazetteer is built for this case's dataset's unit yet: an administrator builds one in " +
    "Admin › Maps.",
};

type Panel =
  | { state: "loading" }
  | { state: "failed"; words: string }
  | GazetteerPanelState;

export function CaseGazetteerPanel({ load, add, remove, mayChange, onChanged }: CaseGazetteerPanelProps) {
  const headingId = useId();
  const [panel, setPanel] = useState<Panel>({ state: "loading" });
  const [words, setWords] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    load().then(
      (state) => current && setPanel(state),
      (err: unknown) =>
        current &&
        setPanel({
          state: "failed",
          words: err instanceof GazetteersFailed ? err.message : "The gazetteers could not be read.",
        }),
    );
    return () => {
      current = false;
    };
  }, [load]);

  async function toggle(datasetId: string, gazetteer: CaseGazetteer) {
    setBusy(true);
    setWords(gazetteer.added ? `Removing ${gazetteer.name}…` : `Adding ${gazetteer.name}…`);
    try {
      const answer = gazetteer.added
        ? await remove(datasetId, gazetteer.dataset_id)
        : await add(datasetId, gazetteer.dataset_id);
      setPanel({ state: "ready", datasetId, gazetteers: answer.gazetteers });
      setWords(
        answer.said ??
          (gazetteer.added
            ? `${gazetteer.name} is removed.`
            : `${gazetteer.name} is added: its places are copied into this case's dataset, and the ` +
              "place search offers them."),
      );
      onChanged();
    } catch (err) {
      setWords(err instanceof GazetteersFailed ? err.message : "The gazetteer could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="map-controls__gazetteers" aria-labelledby={headingId}>
      <h3 id={headingId} className="map-controls__legend">
        Gazetteers in this case's dataset
      </h3>
      {panel.state === "loading" && <p className="map-controls__note">Reading the gazetteers…</p>}
      {panel.state === "failed" && <p className="map-controls__note">{panel.words}</p>}
      {panel.state !== "loading" && panel.state !== "failed" && panel.state !== "ready" && (
        <p className="map-controls__note">{EMPTY_WORDS[panel.state]}</p>
      )}
      {panel.state === "ready" && (
        <ul className="map-controls__gazetteer-list" aria-label="Gazetteers">
          {panel.gazetteers.map((gazetteer) => (
            <li key={gazetteer.dataset_id} className="map-controls__row">
              <span>
                {gazetteer.name}
                <span className="map-controls__state">
                  {gazetteer.added ? " — added" : " — not added"}
                </span>
              </span>
              {mayChange && (
                <button
                  type="button"
                  className="btn btn--quiet"
                  disabled={busy}
                  aria-label={`${gazetteer.added ? "Remove" : "Add"} ${gazetteer.name}`}
                  onClick={() => void toggle(panel.datasetId, gazetteer)}
                >
                  {gazetteer.added ? "Remove" : "Add"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {panel.state === "ready" && !mayChange && (
        <p className="map-controls__note">
          Adding or removing a gazetteer needs the right to run pipelines.
        </p>
      )}
      <div role="status" className="map-controls__words">
        {words}
      </div>
    </section>
  );
}
