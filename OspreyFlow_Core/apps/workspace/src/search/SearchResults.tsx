// The search results page (the owner's navigation decision of 13 November 2026, Part A; ADR-145 Amendment 15 Part A).
// Results fill the main area: a back link to the view the person left, the heading with the Conduit's total in
// records, the groups with their counts, the filters the search service offers, each result named as the canvas names
// it (nodeLabel) with why it matched and, for a document, its passage; Show on graph and, for a document, Open; and one
// line at the end handing the words to Ask & Chat. Every count is the Conduit's (`POST …/search`, built against
// `packages/schemas/search.py`): the Glass never counts what it was sent (rule 7).
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

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
  /** The Ask line: Ask & Chat with the words carried over; nothing is sent until the person presses Ask. Absent for
   * someone Ask & Chat is not offered to (no ask_model): no line. */
  onAsk?: (words: string) => void;
  /** Kept but not drawn (a document opened from the results is read over the view; closing it shows them again). */
  hidden?: boolean;
  /** Drawn over the results (Help's keys panel), where the view beneath cannot be reached. */
  beside?: ReactNode;
}

interface Filters {
  datasets: string[];
  dateFrom: string;
  dateTo: string;
}

/** FastAPI refuses a query over the search's limit (`schemas/search.py`'s MAX_QUERY_CHARS) with a list, not words; the
 * page names the limit from it, and the words stay as typed: refused, never cut (rule 2). Any other list says only
 * that the search could not be done: its entries are the framework's words, not the person's. */
function tooLong(detail: unknown, query: string): string | null {
  if (!Array.isArray(detail)) return null;
  const entry = detail.find(
    (d): d is { ctx: { max_length: number } } =>
      typeof d === "object" && d !== null && d.type === "string_too_long" && Array.isArray(d.loc) && d.loc.at(-1) === "query" && typeof d.ctx?.max_length === "number",
  );
  if (!entry) return null;
  return `The search could not be done: a search can be at most ${entry.ctx.max_length} characters, and this one has ${[...query].length}. Shorten it and press Enter again.`;
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
  hidden = false,
  beside = null,
}: SearchResultsProps) {
  const govuk = currentBrand() === "govuk";
  const [group, setGroup] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [answer, setAnswer] = useState<Answer>({ kind: "loading" });
  // The last page answered, drawn while the next is asked for, so the controls a person is on stay where they are.
  const [last, setLast] = useState<SearchPageResponse | null>(null);
  // Next page, Previous page and Clear filters take the person to the top of the new answer: its heading.
  const focusHeadingOnAnswer = useRef(false);
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
        const detail = typeof body?.detail === "string" ? body.detail : tooLong(body?.detail, query);
        setAnswer({ kind: "refused", words: detail ?? `The search could not be done (${response.status}).` });
        return;
      }
      const body = (await response.json()) as SearchPageResponse;
      if (mine !== latest.current) return;
      setAnswer({ kind: "page", page: body });
      setLast(body);
      if (focusHeadingOnAnswer.current) {
        focusHeadingOnAnswer.current = false;
        heading.current?.focus();
      }
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

  const turnTo = (next: number) => {
    focusHeadingOnAnswer.current = true;
    setPage(next);
  };
  const choose = (next: Partial<{ group: string | null; filters: Filters; page: number }>) => {
    if ("group" in next) setGroup(next.group ?? null);
    if (next.filters) setFilters(next.filters);
    setPage(next.page ?? 1);
  };

  const filtered = filters.datasets.length > 0 || filters.dateFrom !== "" || filters.dateTo !== "";
  // Every count is from the latest answer, the filters and the group as they now stand (rule 7).
  const shown = answer.kind === "refused" ? null : last;
  const counts = shown;
  const groupCount = counts && group !== null ? counts.groups.find((g) => g.key === group)?.count : undefined;
  const totalWords = counts
    ? `${records(groupCount ?? counts.total)}${counts.counts_exact ? "" : " (counts may be incomplete)"}`
    : null;
  const askLine = onAsk && (
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
      onClick={() => {
        focusHeadingOnAnswer.current = true;
        choose({ filters: NO_FILTERS });
      }}
    >
      Clear filters
    </button>
  );
  const byId = new Map((shown?.nodes ?? []).map((n) => [n.id, n]));

  return (
    <section className={govuk ? "search-results search-results--govuk" : "search-results"} aria-labelledby={headingId} hidden={hidden}>
      {beside}
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
      {shown?.limited && (
        <p className={govuk ? "govuk-inset-text search-results__limited" : "search-results__limited"}>
          {shown.limited_reason ?? "Results are limited: the search index is not in use."}
        </p>
      )}
      {answer.kind === "refused" && (
        <p role="alert" className={govuk ? "govuk-error-message" : "search-results__problem"}>
          {answer.words}
        </p>
      )}
      <div className="search-results__columns">
        <div className="search-results__main">
          {counts && counts.groups.length > 0 && (
            <div role="group" aria-label="Result groups" className="search-results__groups">
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
          {/* The counts are each group's own, by design (the owner, 14 November 2026): a Document can be in two
              groups, as a Document and as Mentioned in documents, so All need not equal the groups added up. Said
              where there is more than one group; with one, All and it count the same records. */}
          {counts && counts.groups.length > 1 && (
            <p className={govuk ? "govuk-body-s search-results__per-group" : "search-results__per-group"}>
              Each group counts its own records, and a record can be in more than one, so All need not be the groups
              added up.
            </p>
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
            <Pager page={shown.page} more={shown.more} govuk={govuk} onTurn={turnTo} />
          )}
          {answer.kind !== "loading" && askLine}
        </div>
        {counts && (counts.filters.datasets.length > 0 || counts.filters.dates) && (
          <section aria-labelledby={`${headingId}-filters`} className="search-results__filters">
            <h3 id={`${headingId}-filters`} className={govuk ? "govuk-heading-s" : "search-results__subtitle"}>
              Filters
            </h3>
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
                {(["dateFrom", "dateTo"] as const).map((key) =>
                  govuk ? (
                    <GovukDateField
                      key={`${key}-${filters[key] === "" ? "empty" : "set"}`}
                      id={`${headingId}-${key}`}
                      legend={key === "dateFrom" ? "From" : "To"}
                      value={filters[key]}
                      onDate={(date) => choose({ filters: { ...filters, [key]: date } })}
                    />
                  ) : (
                    <div key={key} className="search-results__date">
                      <label htmlFor={`${headingId}-${key}`}>{key === "dateFrom" ? "From" : "To"}</label>
                      <input
                        id={`${headingId}-${key}`}
                        type="date"
                        className="input"
                        min={counts.filters.dates?.earliest ?? undefined}
                        max={counts.filters.dates?.latest ?? undefined}
                        value={filters[key]}
                        onChange={(e) => choose({ filters: { ...filters, [key]: e.target.value } })}
                      />
                    </div>
                  ),
                )}
              </fieldset>
            )}
            {filtered && clear}
          </section>
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
  // Rule 2: a record the result names that the answer does not hold is said, never dropped in silence.
  const unread = result.node_ids.length - nodes.length;
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
      {unread > 0 && (
        <p className={govuk ? "govuk-body-s search-results__meta" : "search-results__meta"}>
          {`${unread} of its ${result.node_ids.length} records could not be read.`}
        </p>
      )}
      <div className="search-results__actions">
        <button type="button" className={action} aria-label={`Show on graph: ${name}`} disabled={nodes.length === 0} onClick={() => onShow(nodes)}>
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

/** *Next page* and *Previous page*: GOV.UK's pagination under that brand (its links), buttons otherwise. */
function Pager({ page, more, govuk, onTurn }: { page: number; more: boolean; govuk: boolean; onTurn: (page: number) => void }) {
  if (govuk) {
    const link = (to: number, rel: "prev" | "next", words: string) => (
      <a
        className="govuk-link govuk-pagination__link"
        href={`#page-${to}`}
        rel={rel}
        onClick={(e) => {
          e.preventDefault();
          onTurn(to);
        }}
      >
        <span className="govuk-pagination__link-title">
          {words}{" "}
          <span className="govuk-visually-hidden">page</span>
        </span>
      </a>
    );
    return (
      <nav className="govuk-pagination govuk-pagination--block" aria-label="Pages">
        {page > 1 && <div className="govuk-pagination__prev">{link(page - 1, "prev", "Previous")}</div>}
        {more && <div className="govuk-pagination__next">{link(page + 1, "next", "Next")}</div>}
      </nav>
    );
  }
  return (
    <nav aria-label="Pages" className="search-results__pages">
      {page > 1 && (
        <button type="button" className="search-results__link" onClick={() => onTurn(page - 1)}>
          Previous page
        </button>
      )}
      <span className="caption">{`Page ${page}`}</span>
      {more && (
        <button type="button" className="search-results__link" onClick={() => onTurn(page + 1)}>
          Next page
        </button>
      )}
    </nav>
  );
}

/** GOV.UK's date input (day, month, year): the date is sent once the three make a real day, and cleared when emptied. */
function GovukDateField({ id, legend, value, onDate }: { id: string; legend: string; value: string; onDate: (date: string) => void }) {
  const [year, month, day] = value ? value.split("-") : ["", "", ""];
  const [parts, setParts] = useState({ day: day ? String(Number(day)) : "", month: month ? String(Number(month)) : "", year: year ?? "" });
  const change = (part: "day" | "month" | "year", text: string) => {
    const next = { ...parts, [part]: text.trim() };
    setParts(next);
    if (next.day === "" && next.month === "" && next.year === "") {
      if (value !== "") onDate("");
      return;
    }
    const [d, m, y] = [Number(next.day), Number(next.month), Number(next.year)];
    if (!/^\d{4}$/.test(next.year) || !Number.isInteger(d) || !Number.isInteger(m)) return;
    const date = new Date(Date.UTC(y, m - 1, d));
    if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return;
    onDate(date.toISOString().slice(0, 10));
  };
  const field = (part: "day" | "month" | "year", label: string, width: string) => (
    <div className="govuk-date-input__item">
      <div className="govuk-form-group">
        <label className="govuk-label govuk-date-input__label" htmlFor={`${id}-${part}`}>
          {label}
        </label>
        <input
          id={`${id}-${part}`}
          className={`govuk-input govuk-date-input__input ${width}`}
          type="text"
          inputMode="numeric"
          value={parts[part]}
          onChange={(e) => change(part, e.target.value)}
        />
      </div>
    </div>
  );
  return (
    <div className="govuk-form-group">
      <fieldset className="govuk-fieldset" role="group" aria-label={legend}>
        <legend className="govuk-fieldset__legend govuk-fieldset__legend--s">{legend}</legend>
        <div className="govuk-date-input" id={id}>
          {field("day", "Day", "govuk-input--width-2")}
          {field("month", "Month", "govuk-input--width-2")}
          {field("year", "Year", "govuk-input--width-4")}
        </div>
      </fieldset>
    </div>
  );
}
