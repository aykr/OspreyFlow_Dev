// The context banner (ADR-145 decision 2): one line under the top bar naming the place the person is
// in and what they are working on — "You are in the Glass · Case Kestrel ▾ · reads Prison intel";
// "You are in the Ingest Studio · for case Kestrel ▾"; "You are in Rules and Monitoring · Case Kestrel
// ▾" (ADR-145 Amendment 4 decision 1); "You are in Admin".
// A person who holds both the Glass and the Studio gets the cross-link between them, which keeps the
// case they came from. Under the GOV.UK brand it is a GOV.UK notification banner (decision 3), folded
// into one row (ADR-132 Amendment 8).
//
// In the Glass the banner carries the place's mode toggle, Graph · Drawing board (decision 1, named so
// by Amendment 13; Monitoring left for Rules and Monitoring, ADR-146 decision 2), with the open mode's
// one-line note (Amendment 13), part of the region and its description, so a screen reader reads it
// with the region. A section with no `onSelect` is drawn as coming. Not drawn in the Studio: its dataset
// ("Dataset ‹name› ▾"), which the Studio chooses itself, in its own *Dataset* select
// (`ingest/IngestStudio.tsx`, Lane 1's) — the banner would need a hook there to name it — and that
// dataset's "feeds n cases" (no route gives a dataset's cases as the reader may see them, and an
// unfiltered count is refused by rule 7; `02_GLASS_FRONTEND.md` §2.0a).
import { useEffect, useState, type ReactNode } from "react";

import { currentBrand } from "../brand/brand";
import { caseDatasets, caseLabel, listCases } from "../investigation/cases";
import { PLACE_NAME, type PlaceId } from "./places";
import "./places.css";

export interface CrossLink {
  label: string;
  onFollow: () => void;
}

export interface BannerSection {
  id: string;
  label: string;
  current: boolean;
  /** Absent: the section is coming, drawn but not yet usable. */
  onSelect?: () => void;
  /** How many are open there; none drawn for nothing. */
  badge?: number;
}

export interface ContextBannerProps {
  place: PlaceId;
  /** The place's sections (the Glass's Graph · Drawing board, ADR-145 Amendment 13). */
  sections?: readonly BannerSection[];
  /** One line saying what the open mode is (ADR-145 Amendment 13): in the row when it fits there,
   * under it when it does not; the region's description either way. */
  note?: string;
  /** The case switcher, in the Glass and the Studio. */
  caseSwitcher?: ReactNode;
  /** The names of the datasets the open case reads; `null` while read or when refused. */
  datasets?: readonly string[] | null;
  crossLink?: CrossLink | null;
}

/** The Glass's two modes in one line each (ADR-145 Amendment 13, the owner's words of 13 November 2026):
 * the graph is the case's data; a drawing board is a sketch beside it. */
export const MODE_NOTE = {
  graph: "Graph: the case's data. Saved views are under Views or Cases.",
  board: "Drawing board: your sketch; it does not change the case's data.",
} as const;

/** The Glass's views that show the case's data (ADR-145 Amendment 13: "on the graph (any view of the case's
 * data)"). On any other Glass view (Dashboards with its Alert monitoring board, Ownership, Connection
 * strength: places on the rail) neither mode is current and neither note is said, so the rail marks the
 * place alone (ADR-145 Amendment 14 decision 3, the owner's "one place, one marker"). */
export const CASE_DATA_VIEWS: readonly string[] = ["graph", "map", "matrix", "reports", "dossier"];

/** Which of the Glass's two modes a view is: `null` for a place of its own on the rail. */
export function glassMode(view: string): keyof typeof MODE_NOTE | null {
  if (view === "boards") return "board";
  return CASE_DATA_VIEWS.includes(view) ? "graph" : null;
}

const YOU_ARE_IN: Record<PlaceId, string> = {
  glass: `You are in ${PLACE_NAME.glass.replace(/^The /, "the ")}`,
  ingest: `You are in the ${PLACE_NAME.ingest}`,
  rules: `You are in ${PLACE_NAME.rules}`,
  admin: `You are in ${PLACE_NAME.admin}`,
};

function names(datasets: readonly string[]): string {
  return datasets.length <= 1 ? (datasets[0] ?? "") : `${datasets.slice(0, -1).join(", ")} and ${datasets[datasets.length - 1]}`;
}

/** The open case's name and the names of the datasets it reads, as the reader may see them (each
 * route's own scope); `null` for either while it is read or when it is refused. */
export function useCaseContext(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string | null,
): { name: string | null; datasets: string[] | null } {
  const [read, setRead] = useState<{ id: string; name: string | null; datasets: string[] | null } | null>(null);
  useEffect(() => {
    if (!investigationId) return;
    let live = true;
    void Promise.all([
      caseDatasets(apiBaseUrl, bearerToken, investigationId).then((d) => d.map((x) => x.name)).catch(() => null),
      listCases(apiBaseUrl, bearerToken)
        .then((cases) => {
          const found = cases.find((c) => c.id === investigationId);
          return found ? caseLabel(found) : null;
        })
        .catch(() => null),
    ]).then(([datasets, name]) => live && setRead({ id: investigationId, name, datasets }));
    return () => {
      live = false;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);
  return read && read.id === investigationId ? read : { name: null, datasets: null };
}

export function ContextBanner({ place, sections = [], caseSwitcher, datasets, note, crossLink }: ContextBannerProps) {
  const govuk = currentBrand() === "govuk";
  // The place opens the line in both brands (ADR-132 Amendment 8 folded GOV.UK's title into it), so each
  // part after it is set off by a separator.
  const next = () => <span className="context-banner__sep" aria-hidden="true">·</span>;
  const described = note ? "context-banner-note" : undefined;
  const line = (
    <>
      {sections.length > 0 && (
        <>
          {next()}
          <nav aria-label={`In ${PLACE_NAME[place].replace(/^The /, "the ")}`} className="context-banner__sections">
            {sections.map((section) => (
              <button
                key={section.id}
                type="button"
                className={govuk ? "govuk-link context-banner__section" : "context-banner__section"}
                aria-current={section.current ? "page" : undefined}
                aria-disabled={section.onSelect ? undefined : "true"}
                onClick={section.onSelect}
              >
                {section.onSelect ? section.label : `${section.label} (coming)`}
                {/* The count's name is its visible text and "open", so the visible label stays in the
                    accessible name (WCAG 2.5.3): "Monitoring 3 open". */}
                {section.badge ? (
                  <>
                    {" "}
                    <span className="value context-banner__badge">{section.badge > 99 ? "99+" : section.badge.toLocaleString("en-GB")}</span>
                    {" "}
                    <span className="visually-hidden">open</span>
                  </>
                ) : null}
              </button>
            ))}
          </nav>
        </>
      )}
      {(place === "glass" || place === "rules") && caseSwitcher && (
        <>
          {next()}
          {caseSwitcher}
        </>
      )}
      {/* ADR-145 Amendment 14 decision 4: a case reading none says so here, as the scope badge's NO DATA did
          (ADR-115 Amendment 1 point 5); while the datasets are read or refused, nothing, and the badge stays. */}
      {place === "glass" && datasets && (
        <>
          {next()}
          <span>{datasets.length > 0 ? `reads ${names(datasets)}` : "reads no dataset"}</span>
        </>
      )}
      {place === "ingest" && caseSwitcher && (
        <>
          {next()}
          <span>for</span>
          {caseSwitcher}
        </>
      )}
      {note && (
        <>
          {next()}
          <span id="context-banner-note" className="context-banner__note">
            {note}
          </span>
        </>
      )}
      {crossLink && (
        <button type="button" className={govuk ? "govuk-link context-banner__cross" : "btn btn--ghost context-banner__cross"} onClick={crossLink.onFollow}>
          {crossLink.label}
        </button>
      )}
    </>
  );
  if (govuk) {
    // ADR-132 Amendment 8 (the owner's ruling, 13 November 2026): one row, not GOV.UK's title band over its
    // content. "You are in …" is still the region's heading and name, at the start of the row, at its size.
    return (
      <div className="govuk-notification-banner context-banner--govuk context-banner--folded" role="region" aria-labelledby="context-banner-title" aria-describedby={described}>
        <div className="govuk-notification-banner__content">
          <h2 className="govuk-notification-banner__title context-banner__place" id="context-banner-title">
            {YOU_ARE_IN[place]}
          </h2>
          {line}
        </div>
      </div>
    );
  }
  return (
    <div className="context-banner" role="region" aria-labelledby="context-banner-title" aria-describedby={described}>
      <h2 className="context-banner__place" id="context-banner-title">
        {YOU_ARE_IN[place]}
      </h2>
      {line}
    </div>
  );
}

/** The cross-link between the Glass and the Studio for a person who holds both (decision 2): from
 * the Glass, to the Studio on the same case (its words not naming the datasets, Amendment 14); from the Studio, back to the case in the Glass. */
export function crossLinkFor(
  place: PlaceId,
  places: readonly PlaceId[],
  caseName: string | null,
  datasets: readonly string[] | null,
  go: { toStudio: () => void; toGlass: () => void },
): CrossLink | null {
  if (!places.includes("glass") || !places.includes("ingest")) return null;
  if (place === "glass") {
    // ADR-145 Amendment 14 decision 4: the row names the case's datasets once, in "reads …"; the
    // cross-link does not name them again.
    return { label: "Open this case's data in the Ingest Studio ↗", onFollow: go.toStudio };
  }
  if (place === "ingest") {
    return { label: caseName ? `← Back to case ${caseName} in the Glass` : "← Back to the case in the Glass", onFollow: go.toGlass };
  }
  return null;
}
