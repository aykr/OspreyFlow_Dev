// The context banner (ADR-145 decision 2): one line under the top bar naming the place the person is
// in and what they are working on — "You are in the Glass · Case Kestrel ▾ · reads Prison intel";
// "You are in the Ingest Studio · for case Kestrel ▾"; "You are in Rules and Monitoring · Case Kestrel
// ▾" (ADR-145 Amendment 4 decision 1); "You are in Admin".
// A person who holds both the Glass and the Studio gets the cross-link between them, which keeps the
// case they came from. Under the GOV.UK brand it is a GOV.UK notification banner (decision 3), folded
// into one row (ADR-132 Amendment 8).
//
// In the Glass the banner is the case line (the owner's navigation decision of 13 November 2026, ADR-145
// Amendment 15, replacing Amendment 13's mode toggle and note; its words ADR-145 Amendment 17's): "Case ‹switcher›
// › Saved view: ‹name› · Saved views (n) · reads …", the saved view named only while one is open.
// Graph, Map, Drawing board and Reports are the top bar's one view switch. `sections` and `note` remain for a
// place that has them; the Glass passes none. A section with no `onSelect` is drawn as coming. Not drawn in the Studio: its dataset
// ("Dataset ‹name› ▾"), which the Studio chooses itself, in its own *Dataset* select
// (`ingest/IngestStudio.tsx`, Lane 1's) — the banner would need a hook there to name it — and that
// dataset's "feeds n cases" (no route gives a dataset's cases as the reader may see them, and an
// unfiltered count is refused by rule 7; `02_GLASS_FRONTEND.md` §2.0a).
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { flushSync } from "react-dom";

import { currentBrand } from "../brand/brand";
import { CaseStateItems, SavedViewDetails, type CaseState } from "../views/SavedViewOnTheLine";
import { caseDatasets, caseLabel, listCases } from "../investigation/cases";
import { PLACE_NAME, type PlaceId } from "./places";
import "./places.css";

export interface CrossLink {
  label: string;
  /** Its words when the line runs out of room (the owner's word of 15 November 2026: the line stays one line where the
   * top bar does), the place it goes to and no more: the case is the one the line names. */
  shortLabel?: string;
  /** Its shortest words, on the slim line's last fold step before any wrap (ADR-145 Amendment 19 decision 6, the
   * owner's ruling 14), with the name a screen reader hears, which holds those words (WCAG 2.5.3). */
  shortest?: { label: string; name: string };
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
  /** The case line's *Saved views (n)* (ADR-145 Amendment 17, amending Amendment 15's *Views in this case*): opens the
   * saved views panel. In the Glass only. */
  onViews?: () => void;
  /** Whether the panel *Saved views* opens is open (its `aria-expanded`). */
  viewsOpen?: boolean;
  /** How many saved views of the case this reader may see, for *Saved views (n)*; `null` while read or refused. */
  savedViews?: number | null;
  /** What is on the canvas (ADR-145 Amendment 19 decisions 1–2, replacing Amendment 17's strip and its "› Saved view"):
   * "Whole case", or the saved view open with its tag, *Details* and *Back to the whole case*; none, nothing (a place
   * or a view with no canvas). */
  caseState?: CaseState | null;
  /** ADR-145 Amendment 19 decision 6: the slim line, while the view's toolbar is hidden. "You are in …" is kept for a
   * screen reader only (it still names the region), "reads …" is not drawn, and the cross-link keeps its short words. */
  slim?: boolean;
  /** Drawn last on the line (Amendment 19 decision 6: *Show toolbar* at its right end, where *Hide toolbar* was). */
  end?: ReactNode;
}

/** The case line's *Saved views* button, where focus goes back to from the strip's *Back to the whole case* and from the
 * panel's *The whole case* (ADR-145 Amendment 17). */
export const SAVED_VIEWS_BUTTON = "[data-saved-views-button]";
export function focusSavedViewsButton(): void {
  document.querySelector<HTMLElement>(SAVED_VIEWS_BUTTON)?.focus();
}

/** The case line's button's words: *Saved views (n)*, n as the reader may see them; *Saved views* while unread. */
export function savedViewsLabel(count: number | null | undefined): string {
  return typeof count === "number" ? `Saved views (${count.toLocaleString("en-GB")})` : "Saved views";
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

/** `TopBar`'s `barWraps` over the line's own items: whether any of them starts below the first row. *Details*, drawn over
 * the canvas (`data-off-line`), is not one of them. */
function lineWraps(line: HTMLElement): boolean {
  const boxes = [...line.children]
    .filter((child) => !child.hasAttribute("data-off-line"))
    .map((child) => child.getBoundingClientRect())
    .filter((box) => box.width > 0 && box.height > 0);
  if (boxes.length < 2) return false;
  const firstRowBottom = Math.min(...boxes.map((box) => box.bottom));
  return boxes.some((box) => box.top >= firstRowBottom - 0.5);
}

export function ContextBanner({ place, sections = [], caseSwitcher, datasets, note, crossLink, onViews, viewsOpen = false, savedViews, caseState = null, slim = false, end }: ContextBannerProps) {
  const govuk = currentBrand() === "govuk";
  // The line stays one line where the top bar does (the owner's word and ruling, 15 November 2026), measured as the top
  // bar folds (`lineWraps`, `TopBar`'s rule over the line's own items), in steps (ADR-145 Amendment 19 decision 4): 0,
  // everything at its full words; 1, the cross-link's short words; 2, "reads …" ellipsized (its whole words in its
  // title); 3, "reads …" out of sight (kept for a screen reader) and the open saved view's name ellipsized; 4, the case
  // switcher ellipsized too (its whole name in its title and its accessible name, down to 8em); 5, "You are in …" out
  // of sight, still the region's name (the owner's ruling 10, 16 November 2026); 6, if even that cannot hold one line,
  // whole items wrap, the cross-link still short. *Saved views (n)*, *Details*, the tag and *Back to the whole case*
  // never fold. Again from 0 whenever the line's width changes or a web font arrives.
  const row = useRef<HTMLDivElement>(null);
  const [fold, setFold] = useState({ step: 0, pass: 0 });
  const shortLabel = crossLink?.shortLabel;
  // The slim line has one more step before it wraps (ruling 14): the cross-link's shortest words, so it is never taller
  // than the full line, which has "You are in …" and "reads …" to give way where the slim line has *Show toolbar*.
  const lastSqueeze = slim && crossLink?.shortest ? 6 : 5;
  useLayoutEffect(() => {
    const element = row.current;
    if (!element) return;
    if (fold.step < 2 && lineWraps(element)) setFold((current) => ({ ...current, step: current.step === 0 && shortLabel ? 1 : 2 }));
    else if (fold.step >= 2 && fold.step <= lastSqueeze && element.scrollWidth > element.clientWidth + 1)
      setFold((current) => ({ ...current, step: current.step + 1 }));
  }, [fold.step, fold.pass, shortLabel, crossLink?.label, datasets, place, caseState, slim, lastSqueeze]);
  useLayoutEffect(() => {
    const element = row.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    let width = element.clientWidth;
    const again = () => flushSync(() => setFold((current) => ({ step: 0, pass: current.pass + 1 })));
    const observer = new ResizeObserver(() => {
      if (element.clientWidth !== width) {
        width = element.clientWidth;
        again();
      } else if (lineWraps(element)) {
        flushSync(() => setFold((current) => (current.step < 2 ? { ...current, step: current.step + 1 } : current)));
      }
    });
    observer.observe(element);
    const fonts = typeof document !== "undefined" ? document.fonts : undefined;
    let live = true;
    fonts?.addEventListener?.("loadingdone", again);
    void fonts?.ready?.then(() => live && again());
    return () => {
      live = false;
      observer.disconnect();
      fonts?.removeEventListener?.("loadingdone", again);
    };
  }, []);
  // The slim and full lines fold from their own start: a step the one reached means something else in the other.
  const wasSlim = useRef(slim);
  useLayoutEffect(() => {
    if (wasSlim.current === slim) return;
    wasSlim.current = slim;
    setFold((current) => ({ step: 0, pass: current.pass + 1 }));
  }, [slim]);
  const short = slim || fold.step >= 1;
  const squeezed = fold.step >= 2 && fold.step <= lastSqueeze;
  const shortest = squeezed && fold.step >= 6 && crossLink?.shortest ? crossLink.shortest : null;
  const rowClass = [squeezed && "context-banner--squeezed", squeezed && fold.step >= 4 && "context-banner--fold-case"].filter(Boolean).join(" ");
  const placeHidden = slim || (squeezed && fold.step >= 5);
  // *Details* of the open saved view (Amendment 19 decision 2): closed again whenever another view opens, and focus
  // back on its button when Esc closes it.
  const [details, setDetails] = useState<{ open: boolean; id: string | null }>({ open: false, id: null });
  const viewId = caseState && caseState !== "whole" ? caseState.id : null;
  const detailsOpen = details.open && details.id === viewId && viewId !== null;
  const detailsButton = useRef<HTMLButtonElement>(null);
  const closeDetails = () => {
    setDetails({ open: false, id: viewId });
    detailsButton.current?.focus();
  };
  // Esc anywhere on the line, *Details* itself included, closes it while it is open (a disclosure's own key).
  const onLineKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Escape" || !detailsOpen) return;
    event.stopPropagation();
    closeDetails();
  };
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
      {place === "glass" && caseSwitcher && (
        // The owner's navigation decision (ADR-145 Amendment 15, its words Amendment 17's): "Case ‹switcher› · Saved views (n) · reads …",
        // with the word "Case" visible; the switcher's name keeps its own "Case:" for a screen reader.
        <>
          {/* No separator before "Case" while "You are in …" is out of sight (the slim line, fold step 5). */}
          {!placeHidden && next()}
          <span className="context-banner__label" aria-hidden="true">Case</span>
          {caseSwitcher}
          {onViews && (
            <>
              {next()}
              <button
                type="button"
                className={govuk ? "govuk-link context-banner__section" : "context-banner__section"}
                aria-haspopup="dialog"
                aria-expanded={viewsOpen}
                data-saved-views-button=""
                onClick={onViews}
              >
                {savedViewsLabel(savedViews)}
              </button>
            </>
          )}
          {/* ADR-145 Amendment 19: what is on the canvas, after *Saved views (n)*. */}
          {caseState && (
            <CaseStateItems
              state={caseState}
              govuk={govuk}
              sep={next}
              fitName={squeezed && fold.step >= 3}
              detailsOpen={detailsOpen}
              onDetails={() => setDetails({ open: !detailsOpen, id: viewId })}
              detailsButton={detailsButton}
            />
          )}
        </>
      )}
      {place === "rules" && caseSwitcher && (
        <>
          {next()}
          {caseSwitcher}
        </>
      )}
      {/* ADR-145 Amendment 14 decision 4: a case reading none says so here, as the scope badge's NO DATA did
          (ADR-115 Amendment 1 point 5); while the datasets are read or refused, nothing, and the badge stays. */}
      {place === "glass" && datasets && !slim && (
        <>
          {next()}
          <span
            className={squeezed && fold.step >= 3 ? "context-banner__reads visually-hidden" : squeezed ? "context-banner__reads context-banner__fit" : "context-banner__reads"}
            title={datasets.length > 0 ? `reads ${names(datasets)}` : undefined}
          >
            {datasets.length > 0 ? `reads ${names(datasets)}` : "reads no dataset"}
          </span>
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
        <button
          type="button"
          className={govuk ? "govuk-link context-banner__cross" : "btn btn--ghost context-banner__cross"}
          aria-label={shortest ? shortest.name : undefined}
          onClick={crossLink.onFollow}
        >
          {shortest ? shortest.label : short && crossLink.shortLabel ? crossLink.shortLabel : crossLink.label}
        </button>
      )}
      {end && <span className="context-banner__end">{end}</span>}
      {/* Over the canvas, under the line: off the line's own row, so it neither folds the line nor moves the canvas. */}
      {detailsOpen && caseState && caseState !== "whole" && <SavedViewDetails state={caseState} govuk={govuk} />}
    </>
  );
  if (govuk) {
    // ADR-132 Amendment 8 (the owner's ruling, 13 November 2026): one row, not GOV.UK's title band over its
    // content. "You are in …" is still the region's heading and name, at the start of the row, at its size.
    return (
      <div className="govuk-notification-banner context-banner--govuk context-banner--folded" role="region" aria-labelledby="context-banner-title" aria-describedby={described}>
        <div ref={row} className={`govuk-notification-banner__content ${rowClass}`.trim()} onKeyDown={onLineKeyDown}>
          <h2 className={placeHidden ? "govuk-notification-banner__title context-banner__place visually-hidden" : "govuk-notification-banner__title context-banner__place"} id="context-banner-title">
            {YOU_ARE_IN[place]}
          </h2>
          {line}
        </div>
      </div>
    );
  }
  return (
    <div ref={row} className={`context-banner ${rowClass}`.trim()} role="region" aria-labelledby="context-banner-title" aria-describedby={described} onKeyDown={onLineKeyDown}>
      <h2 className={placeHidden ? "context-banner__place visually-hidden" : "context-banner__place"} id="context-banner-title">
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
    return {
      label: "Open this case's data in the Ingest Studio ↗",
      shortLabel: "Open in the Ingest Studio ↗",
      shortest: { label: "Studio ↗", name: "Open in the Ingest Studio" },
      onFollow: go.toStudio,
    };
  }
  if (place === "ingest") {
    return {
      label: caseName ? `← Back to case ${caseName} in the Glass` : "← Back to the case in the Glass",
      shortLabel: "← Back to the Glass",
      onFollow: go.toGlass,
    };
  }
  return null;
}
