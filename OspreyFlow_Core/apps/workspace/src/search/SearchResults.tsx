// The search results page (the owner's navigation decision of 13 November 2026, Part A; ADR-145 Amendment 15 Part A).
// Results fill the main area: a back link to the view the person left, the heading with the Conduit's total in
// records, the groups with their counts, the filters the search service offers, each result named as the canvas names
// it (nodeLabel) with why it matched and, for a document, its passage; Show on graph and, for a document, Open; and one
// line at the end handing the words to Ask & Chat. Every count is the Conduit's (`POST …/search`, built against
// `packages/schemas/search.py`): the Glass never counts what it was sent (rule 7).
import { useCallback, useEffect, useId, useRef, useState } from "react";

import type { Node, SearchPageResponse, SearchResult } from "../../../../packages/schemas/generated";
import { currentBrand } from "../brand/brand";
import { nodeLabel } from "../canvas/nodeAttributes";
import "./searchResults.css";

/** One page of results. The frozen shape allows 1–50; 20 keeps a page to one screen of reading. */
export const RESULTS_PAGE_SIZE = 20;

export interface SearchResultsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  query: string;
  /** The view the person left, by its name ("Graph"), for the back link. */
  backLabel: string;
  onBack: () => void;
  /** Show on graph: every record the result stands for. */
  onShow: (nodes: Node[]) => void;
  /** Open, for a document: the reader with its first record. */
  onOpenDocument: (nodeId: string) => void;
  /** The Ask line: Ask & Chat with the words carried over; nothing is sent until the person presses Ask. */
  onAsk: (words: string) => void;
}

interface Filters {
  datasets: string[];
  dateFrom: string;
  dateTo: string;
}

const NO_FILTERS: Filters = { datasets: [], dateFrom: "", dateTo: "" };

function requestFilters(filters: Filters): Record<string, unknown> {
  return {
    ...(filters.datasets.length > 0 ? { datasets: filters.datasets } : {}),
    ...(filters.dateFrom ? { date_from: filters.dateFrom } : {}),
    ...(filters.dateTo ? { date_to: filters.dateTo } : {}),
  };
}

function records(n: number): string {
  return `${n.toLocaleString("en-GB")} ${n === 1 ? "record" : "records"}`;
}

type Answer = { kind: "loading" } | { kind: "page"; page: SearchPageResponse } | { kind: "refused"; words: string };

export function SearchResults({
  apiBaseUrl,
  bearerToken,
  investigationId,
  query,
  backLabel,
  onBack,
  onShow,
  onOpenDocument,
  onAsk,
}: SearchResultsProps) {
  const govuk = currentBrand() === "govuk";
  const [group, setGroup] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [answer, setAnswer] = useState<Answer>({ kind: "loading" });
  // The groups and the filters on offer are kept from the last answer that had them, so choosing a group with no
  // results on this page does not take the choices away.
  const [offered, setOffered] = useState<Pick<SearchPageResponse, "groups" | "filters" | "total" | "counts_exact"> | null>(null);
  const latest = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const headingId = useId();

  const ask = useCallback(async () => {
    latest.current += 1;
    const mine = latest.current;
    setAnswer({ kind: "loading" });
    try {
      const response = await fetch(`${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/search`, {
        method: "POST",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ query, group, filters: requestFilters(filters), page, page_size: RESULTS_PAGE_SIZE }),
      });
      if (mine !== latest.current) return;
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
        const detail = typeof body?.detail === "string" ? body.detail : null;
        setAnswer({ kind: "refused", words: detail ?? `The search could not be done (${response.status}).` });
        return;
      }
      const body = (await response.json()) as SearchPageResponse;
      if (mine !== latest.current) return;
      setAnswer({ kind: "page", page: body });
      if (group === null) setOffered({ groups: body.groups, filters: body.filters, total: body.total, counts_exact: body.counts_exact });
    } catch {
      if (mine === latest.current) setAnswer({ kind: "refused", words: "The search could not be done: the Conduit did not answer." });
    }
  }, [apiBaseUrl, bearerToken, investigationId, query, group, filters, page]);

  useEffect(() => {
    void ask();
  }, [ask]);

  // Focus moves to the heading when the page opens (and for a new query), so a screen reader hears where it is.
  useEffect(() => {
    heading.current?.focus();
  }, [query]);

  const choose = (next: Partial<{ group: string | null; filters: Filters; page: number }>) => {
    if ("group" in next) setGroup(next.group ?? null);
    if (next.filters) setFilters(next.filters);
    setPage(next.page ?? 1);
  };

  const filtered = filters.datasets.length > 0 || filters.dateFrom !== "" || filters.dateTo !== "";
  const shown = answer.kind === "page" ? answer.page : null;
  const counts = offered ?? shown;
  const totalWords = counts ? `${records(counts.total)}${counts.counts_exact ? "" : " (counts may be incomplete)"}` : null;
  const askLine = (
    <p className={govuk ? "govuk-body search-results__ask" : "search-results__ask"}>
      <button type="button" className={govuk ? "govuk-link search-results__link" : "search-results__link"} onClick={() => onAsk(query)}>
        {`Ask a question about '${query}' instead`}
      </button>
    </p>
  );
  const clear = (
    <button
      type="button"
      className={govuk ? "govuk-button govuk-button--secondary search-results__clear" : "btn btn--quiet search-results__clear"}
      onClick={() => choose({ filters: NO_FILTERS })}
    >
      Clear filters
    </button>
  );
  const byId = new Map((shown?.nodes ?? []).map((n) => [n.id, n]));

  return (
    <section className={govuk ? "search-results search-results--govuk" : "search-results"} aria-labelledby={headingId}>
      <button type="button" className={govuk ? "govuk-back-link search-results__back" : "search-results__back"} onClick={onBack}>
        {`Back to ${backLabel}`}
      </button>
      <h2 id={headingId} ref={heading} tabIndex={-1} className={govuk ? "govuk-heading-l" : "search-results__title"}>
        {`Search results for '${query}'`}
      </h2>
      {totalWords && <p className={govuk ? "govuk-body search-results__total" : "search-results__total"}>{totalWords}</p>}
      {/* Announced when results load, and again for a group, a filter or a page. */}
      <p role="status" className="visually-hidden">
        {answer.kind === "loading" ? "Searching…" : shown ? `Found ${totalWords ?? ""}${shown.results.length === 0 ? ", none on this page" : ""}` : ""}
      </p>
      {shown?.limited && shown.limited_reason && (
        <p className={govuk ? "govuk-inset-text search-results__limited" : "search-results__limited"}>{shown.limited_reason}</p>
      )}
      {answer.kind === "refused" && (
        <p role="alert" className={govuk ? "govuk-error-message" : "search-results__problem"}>
          {answer.words}
        </p>
      )}
      <div className="search-results__columns">
        <div className="search-results__main">
          {counts && counts.groups.length > 0 && (
            <div role="group" aria-label="Group" className="search-results__groups">
              {[{ key: null, label: "All", count: counts.total }, ...counts.groups].map((g) => (
                <button
                  key={g.key ?? "all"}
                  type="button"
                  className={govuk ? "govuk-button govuk-button--secondary search-results__group" : "search-results__group"}
                  aria-pressed={group === g.key}
                  onClick={() => choose({ group: g.key })}
                >
                  {g.label} <span className="search-results__count">{g.count.toLocaleString("en-GB")}</span>
                </button>
              ))}
            </div>
          )}
          {shown && shown.results.length > 0 && (
            <ul aria-label="Results" className={govuk ? "govuk-list search-results__list" : "search-results__list"}>
              {shown.results.map((result) => (
                <ResultItem
                  key={result.node_ids.join(" ")}
                  result={result}
                  nodes={result.node_ids.map((id) => byId.get(id)).filter((n): n is Node => n !== undefined)}
                  govuk={govuk}
                  onShow={onShow}
                  onOpenDocument={onOpenDocument}
                />
              ))}
            </ul>
          )}
          {shown && shown.results.length === 0 && shown.page === 1 && (
            <div className="search-results__none">
              <p className={govuk ? "govuk-body" : undefined}>{`No records match '${query}'${group === null ? "" : " in this group"}.`}</p>
              {filtered && clear}
            </div>
          )}
          {shown && (shown.page > 1 || shown.more) && (
            <nav aria-label="Pages" className="search-results__pages">
              {shown.page > 1 && (
                <button type="button" className={govuk ? "govuk-link search-results__link" : "search-results__link"} onClick={() => setPage(shown.page - 1)}>
                  Previous page
                </button>
              )}
              <span className={govuk ? "govuk-body-s" : "caption"}>{`Page ${shown.page}`}</span>
              {shown.more && (
                <button type="button" className={govuk ? "govuk-link search-results__link" : "search-results__link"} onClick={() => setPage(shown.page + 1)}>
                  Next page
                </button>
              )}
            </nav>
          )}
          {answer.kind !== "loading" && askLine}
        </div>
        {counts && (counts.filters.datasets.length > 0 || counts.filters.dates) && (
          <div role="group" aria-label="Filters" className="search-results__filters">
            <h3 className={govuk ? "govuk-heading-s" : "search-results__subtitle"}>Filters</h3>
            {counts.filters.datasets.length > 0 && (
              <fieldset className={govuk ? "govuk-fieldset" : "search-results__fieldset"}>
                <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "search-results__legend"}>Datasets</legend>
                <div className={govuk ? "govuk-checkboxes govuk-checkboxes--small" : undefined}>
                  {counts.filters.datasets.map((d) => (
                    <div key={d.id} className={govuk ? "govuk-checkboxes__item" : "search-results__check"}>
                      <input
                        id={`${headingId}-ds-${d.id}`}
                        type="checkbox"
                        className={govuk ? "govuk-checkboxes__input" : undefined}
                        checked={filters.datasets.includes(d.id)}
                        onChange={(e) =>
                          choose({
                            filters: {
                              ...filters,
                              datasets: e.target.checked ? [...filters.datasets, d.id] : filters.datasets.filter((id) => id !== d.id),
                            },
                          })
                        }
                      />
                      <label htmlFor={`${headingId}-ds-${d.id}`} className={govuk ? "govuk-label govuk-checkboxes__label" : undefined}>
                        {d.count === null ? d.name : `${d.name} (${d.count.toLocaleString("en-GB")})`}
                      </label>
                    </div>
                  ))}
                </div>
              </fieldset>
            )}
            {counts.filters.dates && (
              <fieldset className={govuk ? "govuk-fieldset" : "search-results__fieldset"}>
                <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "search-results__legend"}>Dates</legend>
                {(["dateFrom", "dateTo"] as const).map((key) => (
                  <div key={key} className={govuk ? "govuk-form-group" : "search-results__date"}>
                    <label htmlFor={`${headingId}-${key}`} className={govuk ? "govuk-label" : undefined}>
                      {key === "dateFrom" ? "From" : "To"}
                    </label>
                    <input
                      id={`${headingId}-${key}`}
                      type="date"
                      className={govuk ? "govuk-input govuk-input--width-10" : "input"}
                      min={counts.filters.dates?.earliest ?? undefined}
                      max={counts.filters.dates?.latest ?? undefined}
                      value={filters[key]}
                      onChange={(e) => choose({ filters: { ...filters, [key]: e.target.value } })}
                    />
                  </div>
                ))}
              </fieldset>
            )}
            {filtered && clear}
          </div>
        )}
      </div>
    </section>
  );
}

function ResultItem({
  result,
  nodes,
  govuk,
  onShow,
  onOpenDocument,
}: {
  result: SearchResult;
  nodes: Node[];
  govuk: boolean;
  onShow: (nodes: Node[]) => void;
  onOpenDocument: (nodeId: string) => void;
}) {
  const first = nodes[0];
  // The Glass's own name for it, as the canvas draws it (the analyst's per-type label choice holds).
  const name = first ? nodeLabel(first) : result.type;
  const action = govuk ? "govuk-button govuk-button--secondary search-results__action" : "btn btn--quiet search-results__action";
  return (
    <li className="search-results__item">
      <h3 className={govuk ? "govuk-heading-s search-results__name" : "search-results__name"}>{name}</h3>
      <p className={govuk ? "govuk-body-s search-results__meta" : "search-results__meta"}>
        <span>{result.type}</span>
        <span aria-hidden="true"> · </span>
        <span>{result.match.why}</span>
        {result.date && (
          <>
            <span aria-hidden="true"> · </span>
            <span>{result.date}</span>
          </>
        )}
      </p>
      {(result.passage ?? []).length > 0 && (
        <p className={govuk ? "govuk-body-s search-results__passage" : "search-results__passage"}>
          {(result.passage ?? []).map((part, i) => (part.match ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>))}
        </p>
      )}
      <div className="search-results__actions">
        <button type="button" className={action} aria-label={`Show ${name} on the graph`} disabled={nodes.length === 0} onClick={() => onShow(nodes)}>
          Show on graph
        </button>
        {result.is_document && first && (
          <button type="button" className={action} aria-label={`Open ${name}`} onClick={() => onOpenDocument(first.id)}>
            Open
          </button>
        )}
      </div>
    </li>
  );
}
