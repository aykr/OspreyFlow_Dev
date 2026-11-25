/**
 * The words of trends shown together, and the view it is drawn from (slice GR4a; ADR-152 decisions 5, 6, 10 and 12, invariant I21;
 * FUNCTIONS row `reports-figures`; scenario TS). Nothing here is a call or a right: a word, or a function from what the Conduit answered
 * to what the template draws.
 *
 * What a pack and a trend are said in is the shared package's (`packages/glass-shared/src/reports/packText.ts`), imported and never
 * written again here: the sentence of a trend's figures (`trendSentence`), the periods of its window (`periodsOf`, `periodKey`), the
 * day (`formatDay`), the number (`formatNumber`) and the one sentence that says some items are not shown (`WITHHELD_ITEMS_SENTENCE`,
 * ADR-124 decision 9: said once, with no number and never which).
 *
 * **It reads strictly** (the owner's ruling for GR3a of 25 November 2026, carried to every GOV.UK page): a body that lacks a field the
 * generated types (`packages/schemas/generated/PackDraft.ts`, `PublishedPack.ts`) mark required, or holds one of the wrong shape, is
 * not a view (`undefined`), which the page says as "could not be read": never a zero, an empty chart or a part of a page (rule 2). An
 * optional field may be missing; when it is there it must be its type's shape. **Every field of those types is drawn or named, in the
 * scenario, as left out** (the field census, `pack-trends.test.ts` TS8): nothing here carries an identifier, the person who added an
 * item or published a version, or a field the census names as left out into the view.
 *
 * The view keeps every trend item the Conduit sent, in the order it sent them, which is the pack's stored order (a `PackItem` "carries no
 * position: the order of the list is the order"): nothing here sorts, cuts or turns the list round. An item that is not a trend is not
 * this page's, and is not drawn (scenario TS3). Plain words, British English.
 */
import {
  WITHHELD_ITEMS_SENTENCE,
  formatDay,
  formatNumber,
  periodKey,
  periodsOf,
  trendSentence,
} from "@ospreyflow/glass-shared";

/** A trend's figures, as the shared sentence reads them (the generated `TrendFigures`). */
type TrendFigures = Parameters<typeof trendSentence>[0];

export const PACK_TRENDS_WORDS = {
  title: "Trends shown together",
  lede: "The saved trends of one pack, in the pack's order, each as it was counted when it was added. This page only shows them.",
  pack: (title: string): string => `Pack: ${title}`,
  working: "The working pack, as it stands now.",
  published: (version: number, day: string): string => `Published version ${formatNumber(version)}, on ${day}.`,
  withheld: WITHHELD_ITEMS_SENTENCE,
  noTrends: "This pack has no trends to show you.",
  period: (from: string, to: string): string => `From ${from} to ${to}`,
  countedOn: (day: string): string => `Counted on ${day}`,
  marking: (marking: string): string => `Marking: ${marking}`,
  caption: (title: string): string => `The figures of ${title}`,
  weekStarting: "Week starting",
  monthStarting: "Month starting",
  count: "Count",
  sum: (field: string): string => `Sum of ${field}`,
  total: "Total",
  noSeries: "No series",
  chart: (title: string, bars: number, unit: string, from: string, to: string, most: string | undefined, below: boolean): string =>
    `${title}: one bar for each of ${formatNumber(bars)} ${unit}, from ${from} to ${to}; ` +
    (most === undefined ? "no bar has any height, as no total is above zero" : `the tallest bar is ${most}`) +
    (below ? "; a period whose total is below zero has no height, and the table gives every figure." : "."),
  weeks: "weeks",
  months: "months",
  unreadable: "The trends could not be read just now. Nothing is shown, and nothing has changed. Try again in a few minutes.",
  back: "Back to Home",
} as const;

/** One bar of a chart, in the chart's own units (its view box): drawn by attributes of the element and a class, never a style. */
export interface Bar {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TrendView {
  title: string;
  period: string;
  countedOn: string;
  marking: string;
  sentence: string;
  chart: { label: string; width: number; height: number; bars: Bar[] };
  table: { caption: string; columns: string[]; rows: { head: string; cells: string[] }[] };
}

export interface PackTrendsView {
  kind: "trends";
  pack: string;
  standing: string;
  withheld: boolean;
  trends: TrendView[];
}

// ------------------------------------------------------------------------------------------------ the strict reader

type Fields = Record<string, unknown>;
const isObject = (value: unknown): value is Fields => typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === "string";
const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const isDay = (value: unknown): value is string => isText(value) && !Number.isNaN(new Date(value).getTime());
const isList = (value: unknown): value is unknown[] => Array.isArray(value);
/** An optional field: missing, or (when `nullable`) null, or the shape `check` asks. */
const optional = (fields: Fields, name: string, check: (value: unknown) => boolean, nullable = false): boolean =>
  !(name in fields) || fields[name] === undefined || (nullable && fields[name] === null) || check(fields[name]);
const oneOf =
  (...values: string[]) =>
  (value: unknown): boolean =>
    isText(value) && values.includes(value);

const KINDS = oneOf("trend", "assessment", "entity", "note", "alert");
const INTERVALS = oneOf("week", "month");
const MEASURES = oneOf("count", "sum");
const SOURCES = oneOf("events", "alerts");

/** `ReportPack`: every required field there and of its shape. */
function isReportPack(pack: unknown): pack is Fields {
  return (
    isObject(pack) &&
    isText(pack["id"]) &&
    isText(pack["investigation_id"]) &&
    isText(pack["title"]) &&
    isText(pack["created_by"]) &&
    isDay(pack["created_at"]) &&
    isDay(pack["updated_at"]) &&
    optional(pack, "versions", isList)
  );
}

function isPoint(point: unknown): boolean {
  return isObject(point) && isDay(point["period_start"]) && isNumber(point["value"]) && optional(point, "series", isText, true);
}

function isDefinition(definition: unknown): boolean {
  return (
    isObject(definition) &&
    isText(definition["title"]) &&
    optional(definition, "source", SOURCES) &&
    optional(definition, "event_types", isList) &&
    optional(definition, "measure", MEASURES) &&
    optional(definition, "measure_field", isText, true) &&
    optional(definition, "interval", INTERVALS) &&
    optional(definition, "weeks", isNumber) &&
    optional(definition, "group_by", isText, true) &&
    optional(definition, "filters", isList)
  );
}

function isResult(result: unknown): boolean {
  return (
    isObject(result) &&
    INTERVALS(result["interval"]) &&
    MEASURES(result["measure"]) &&
    isList(result["points"]) &&
    result["points"].every(isPoint) &&
    optional(result, "series", (s) => isList(s) && s.every(isText)) &&
    isNumber(result["total"]) &&
    isNumber(result["events"]) &&
    optional(result, "unvalued", isNumber, true) &&
    optional(result, "classifications", isList) &&
    optional(result, "handlings", isList)
  );
}

/** `TrendFigures`: its definition, its result, the day it was counted and the window's first day. */
function isFigures(figures: unknown): figures is TrendFigures {
  return (
    isObject(figures) &&
    isDefinition(figures["definition"]) &&
    isResult(figures["result"]) &&
    isDay(figures["as_of"]) &&
    isDay(figures["window_start"]) &&
    optional(figures, "marking", isText, true)
  );
}

/** `PackItem`: its own required fields; a trend item must carry its figures (a trend with none is not drawn as an empty chart). */
function isItem(item: unknown): item is Fields & { kind: string; marking: string } {
  if (!isObject(item)) return false;
  const own =
    isText(item["id"]) &&
    KINDS(item["kind"]) &&
    isText(item["marking"]) &&
    isText(item["added_by"]) &&
    isDay(item["added_at"]) &&
    optional(item, "trend_id", isText, true) &&
    optional(item, "trend", isObject, true) &&
    optional(item, "note", isText, true) &&
    optional(item, "replaced_at", isDay, true) &&
    optional(item, "replaced_by", isText, true);
  return own && (item["kind"] !== "trend" || isFigures(item["trend"]));
}

// ------------------------------------------------------------------------------------------------ the view

/** The chart's units: each period is a slot this wide, its bar a little narrower, and the tallest bar this high. */
const SLOT = 10;
const BAR = 8;
const TALLEST = 100;

/** One trend's figures as the page draws them: the sentence, a bar for each period of the window and the table of the same figures. */
function trendView(figures: TrendFigures, marking: string): TrendView {
  const { definition, result } = figures;
  const periods = periodsOf(figures);
  // A column for each series, in the result's own order, then any a point names that the result's list does not: never dropped.
  const named = [...(result.series ?? [])];
  for (const point of result.points) {
    const series = point.series ?? "";
    if (point.series !== undefined && point.series !== null && !named.includes(series)) named.push(series);
  }
  const bySeries = named.length > 0;
  const columns = bySeries ? [...named, ...(result.points.some((p) => p.series === null || p.series === undefined) ? [""] : [])] : [""];
  const value = (period: string, series: string): number =>
    result.points.reduce((sum, p) => (periodKey(p.period_start) === period && (bySeries ? (p.series ?? "") === series : true) ? sum + p.value : sum), 0);
  const totals = periods.map((period) => columns.reduce((sum, series) => sum + value(period, series), 0));
  // A bar has no height below zero (a sum of a signed property can total less: `TrendPoint.value` has no lower bound), as the workspace's
  // chart draws it; the table gives the figure, and the text alternative says so rather than a tallest bar the table does not hold.
  const most = totals.reduce((a, b) => Math.max(a, b), 0);
  const below = totals.some((total) => total < 0);
  const measure = result.measure === "sum" ? PACK_TRENDS_WORDS.sum(definition.measure_field ?? "the chosen property") : PACK_TRENDS_WORDS.count;
  const first = formatDay(periods[0] ?? figures.window_start);
  const last = formatDay(periods[periods.length - 1] ?? figures.as_of);
  return {
    title: definition.title,
    period: PACK_TRENDS_WORDS.period(formatDay(figures.window_start), formatDay(figures.as_of)),
    countedOn: PACK_TRENDS_WORDS.countedOn(formatDay(figures.as_of)),
    marking: PACK_TRENDS_WORDS.marking(marking),
    sentence: trendSentence(figures),
    chart: {
      label: PACK_TRENDS_WORDS.chart(definition.title, periods.length, result.interval === "month" ? PACK_TRENDS_WORDS.months : PACK_TRENDS_WORDS.weeks, first, last, most > 0 || !below ? formatNumber(most) : undefined, below),
      width: Math.max(1, periods.length) * SLOT,
      height: TALLEST,
      bars: totals.map((total, i) => {
        const height = most === 0 || total <= 0 ? 0 : Math.round((total / most) * TALLEST * 100) / 100;
        return { x: i * SLOT + (SLOT - BAR) / 2, y: Math.round((TALLEST - height) * 100) / 100, width: BAR, height };
      }),
    },
    table: {
      caption: PACK_TRENDS_WORDS.caption(definition.title),
      columns: [
        result.interval === "month" ? PACK_TRENDS_WORDS.monthStarting : PACK_TRENDS_WORDS.weekStarting,
        ...(bySeries ? [...columns.map((s) => (s === "" ? PACK_TRENDS_WORDS.noSeries : s)), PACK_TRENDS_WORDS.total] : [measure]),
      ],
      rows: periods.map((period, i) => ({
        head: formatDay(period),
        cells: bySeries ? [...columns.map((s) => formatNumber(value(period, s))), formatNumber(totals[i] ?? 0)] : [formatNumber(totals[i] ?? 0)],
      })),
    },
  };
}

/** The view of a pack's items, whichever read they came from: the trends in the order sent, and the yes or no of withheld ones. */
function view(body: Fields, title: string, standing: string): PackTrendsView | undefined {
  const items = body["items"];
  if (!isList(items) || !items.every(isItem) || typeof body["withheld"] !== "boolean" || !optional(body, "marking", isText, true)) return undefined;
  const trends: TrendView[] = [];
  for (const item of items) {
    if (item.kind !== "trend") continue;
    const figures = item["trend"] as TrendFigures;
    trends.push(trendView(figures, item.marking));
  }
  // The pack's own marking (`body["marking"]`) is read (it must be text or null) and not drawn: it is the highest of every kind of item the
  // reader may see, and this page draws the trends alone, so naming it could name a marking higher than anything on the page. Each trend
  // says its own.
  return { kind: "trends", pack: PACK_TRENDS_WORDS.pack(title), standing, withheld: body["withheld"], trends };
}

/** `GET /v1/investigations/{id}/packs/{pack_id}`'s `PackDraft`, or `undefined` when it is not one (said as "could not be read"). */
export function readDraft(body: unknown): PackTrendsView | undefined {
  if (!isObject(body) || !isReportPack(body["pack"])) return undefined;
  return view(body, body["pack"]["title"] as string, PACK_TRENDS_WORDS.working);
}

/** `GET /v1/investigations/{id}/packs/{pack_id}/published`'s `PublishedPack`, or `undefined` when it is not one. */
export function readPublished(body: unknown): PackTrendsView | undefined {
  if (
    !isObject(body) ||
    !isText(body["pack_id"]) ||
    !isText(body["investigation_id"]) ||
    !isText(body["title"]) ||
    !isNumber(body["version"]) ||
    !isDay(body["published_at"]) ||
    !isText(body["published_by"]) ||
    !optional(body, "published_by_name", isText, true)
  ) {
    return undefined;
  }
  const version = body["version"];
  return view(body, body["title"], PACK_TRENDS_WORDS.published(version, formatDay(body["published_at"])));
}
