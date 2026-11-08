// The place switcher (ADR-145 decisions 1 and 3, N6; Amendment 4 decision 1): in the top bar, the
// places the person's rights open, the one they are in marked as the current page. *Rules and
// Monitoring* carries the open-alert count, taken as the reader (ADR-146 decision 2; rule 7), which
// left the Glass's banner. Under the GOV.UK brand it stands inside the
// GOV.UK header instead (ADR-132 Amendment 6): GOV.UK Frontend 6.6.0's header no longer offers
// navigation, so the header carries a small local extension, a slot this switcher is drawn into.
import { useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

import { currentBrand } from "../brand/brand";
import { GOVUK_HEADER_PLACES_ID } from "../brand/govuk/GovukHeader";
import { PLACE_NAME, type PlaceId } from "./places";
import "./places.css";

export interface PlaceSwitcherProps {
  /** The places this person may open (`placesFor`), in order. */
  places: readonly PlaceId[];
  /** The place on screen; `null` on Home, which is no place. */
  current: PlaceId | null;
  onChoose: (place: PlaceId) => void;
  /** How many are open in a place (Rules and Monitoring's alerts); none drawn for nothing. */
  counts?: Partial<Record<PlaceId, number>>;
}

export function PlaceSwitcher({ places, current, onChoose, counts = {} }: PlaceSwitcherProps) {
  const govuk = currentBrand() === "govuk";
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  // The GOV.UK header is drawn above the page by the brand frame; its slot exists once it has been.
  useLayoutEffect(() => {
    setSlot(govuk ? document.getElementById(GOVUK_HEADER_PLACES_ID) : null);
  }, [govuk]);
  if (places.length === 0) return null;
  const nav = (
    <nav aria-label="Places" className={govuk ? "govuk-places" : "place-switcher"}>
      <ul className={govuk ? "govuk-places__list" : "place-switcher__list"}>
        {places.map((place) => (
          <li key={place}>
            <button
              type="button"
              className={govuk ? "govuk-places__item" : "place-switcher__item"}
              aria-current={place === current ? "page" : undefined}
              onClick={() => onChoose(place)}
            >
              {PLACE_NAME[place]}
              {/* The count's name is its visible text and "open", so the visible label stays in the
                  accessible name (WCAG 2.5.3): "Rules and Monitoring 3 open". */}
              {counts[place] ? (
                <>
                  {" "}
                  <span className="value place-switcher__count">{counts[place]! > 99 ? "99+" : counts[place]!.toLocaleString("en-GB")}</span>
                  {" "}
                  <span className="visually-hidden">open</span>
                </>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
  if (govuk) return slot ? createPortal(nav, slot) : null;
  return nav;
}
