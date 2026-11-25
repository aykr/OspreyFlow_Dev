/**
 * The alert monitoring page's words, and the view it is drawn from (slice GR3a; ADR-152 decisions 8 and 10; FUNCTIONS row
 * `reports-figures`; scenario AM). Plain words, British English.
 *
 * **Everything on the page is what the Conduit's report route sent for this reader, and nothing else.** `readReport` and
 * `readLimit` check the route's answer is the shape the figures have and return `undefined` for anything else, so that a body that
 * is not the figures is never drawn in part (rule 2). `monitoringView` only adds up rows the route sent (a week's total is its
 * rows' sum, as the React board adds them) and says them in words; it computes no total of its own, no share of anything the
 * route did not count, and nothing that depends on who is asking: that is the Conduit's, which counts as the reader (rule 3,
 * `services/api/reports.py`).
 *
 * **The chart is plain SVG with classes** (`spec/02` section 2.0f, the owner's ruling of 24 November 2026). `chartOf` gives each
 * bar its row, its geometry and its words: the largest figure is `WIDEST` wide and the others are in proportion. A class cannot say
 * how long a bar is and a `style` attribute is refused (decision 8), so the length is the `width` attribute of the bar's `rect`.
 *
 * The few helpers below are written once more than `packages/glass-shared` has them, because the server's `NodeNext` build cannot
 * import the shared package's extension-less source (see `studioWords.ts`); `test/server/alertMonitoringShared.test.ts` runs each
 * on the same inputs as the shared one, so a copy that drifts is red.
 */

export const PERIODS = [4, 12, 26, 52] as const;
export const DEFAULT_PERIOD = 12;

/** The widest a bar is drawn, in the chart's own units: the largest figure is this wide and the rest are in proportion. */
export const WIDEST = 240;
const VIEW_WIDTH = 520;
const LABEL_RIGHT = 220;
const BAR_LEFT = 230;
const ROW_HEIGHT = 28;
const BAR_HEIGHT = 18;
const TEXT_DROP = 13;

// -------------------------------------------------------------------------------------------------- the shared package's, again

const NUMBER = new Intl.NumberFormat("en-GB");
const DAY = new Intl.DateTimeFormat("en-GB", { dateStyle: "long", timeZone: "UTC" });

/** `packages/glass-shared/src/reports/packText.ts`'s `formatNumber`. */
export function formatNumber(n: number): string {
  return NUMBER.format(n);
}

/** `packages/glass-shared/src/reports/packText.ts`'s `plural`. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${NUMBER.format(n)} ${n === 1 ? one : many}`;
}

/** `packages/glass-shared/src/reports/packText.ts`'s `formatDay`: "11 October 2026"; an unreadable value is shown as it came. */
export function formatDay(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : DAY.format(when);
}

/** `packages/glass-shared/src/alerts/names.ts`'s `TYPOLOGY_LABELS`. */
const TYPOLOGY_LABELS: Record<string, string> = {
  structuring: "Structuring",
  rapid_movement: "Rapid movement",
  circular_flow: "Circular flow",
  kyc_screening: "KYC screening",
  shared_attributes: "Shared contact details",
  document_verification: "Unverified customer",
  pattern: "Drawn pattern",
  sentence: "Sentence rule",
  high_risk_jurisdiction: "High-risk jurisdiction",
  large_cash: "Large cash",
  dormant_reactivated: "Dormant account reactivated",
  velocity_rise: "Sudden rise in velocity",
};

/** `packages/glass-shared/src/alerts/names.ts`'s `typologyLabel`. */
export function typologyLabel(typology: string | null | undefined): string {
  return (typology && TYPOLOGY_LABELS[typology]) || "Alert";
}

/** `packages/glass-shared/src/alerts/closingReasons.ts`'s `CLOSING_REASONS`. */
const CLOSING_REASONS: Record<string, string> = {
  true_positive: "True match",
  false_positive: "False positive",
  duplicate: "Duplicate",
  no_further_action: "No further action",
  referred: "Referred",
};

/** `packages/glass-shared/src/alerts/closingReasons.ts`'s `closingReasonLabel`: "True match"; an unknown value as itself, never hidden. */
export function closingReasonLabel(reason: string | null | undefined): string {
  return reason ? (CLOSING_REASONS[reason] ?? reason) : "";
}

/** `reports/figureParts.tsx`'s `GROUP_NAMES`. */
const GROUP_NAMES: Record<string, string> = { hotlists: "Hotlists", monitors: "Monitors", analyst: "Raised by an analyst", drawn_items: "Drawn items" };

/** `figureParts.tsx`'s `groupName`: a rule group in words, a typology rule by its typology and never a rule's own name. */
export function groupName(label: string, typology: string): string {
  if (label === "typology") return typologyLabel(typology || "other");
  const named = GROUP_NAMES[label];
  if (named) return named;
  const words = label.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// -------------------------------------------------------------------------------------------------- the page's own words

export const ALERT_MONITORING_WORDS = {
  title: "Alert monitoring",
  counted: "Counted for you: an alert concerning anything you cannot see is in no figure here.",
  period: "Period",
  periodLink: (weeks: number): string => `Last ${weeks} weeks`,
  back: "Back to Home",
  raised: (total: number, weeks: number): string => `${plural(total, "alert")} raised in the last ${plural(weeks, "week")}`,
  countedOn: (day: string): string => `Counted on ${day}.`,
  noAlerts: "No alerts were raised in this period.",
  noClosed: "No alerts were closed in this period.",
  tableFollows: "The same figures are in the table below.",
  bars: {
    week: {
      id: "am-raised-each-week",
      heading: "Raised each week",
      caption: "Alerts raised each week",
      columns: ["Week starting", "Alerts raised"],
      title: "Bar chart: alerts raised each week",
      desc: "One bar for each week of the period; the longest bar is the week with most alerts.",
    },
    rule: {
      id: "am-raised-by-rule",
      heading: "Raised by rule",
      caption: "Alerts raised by rule",
      columns: ["Rule", "Alerts raised"],
      title: "Bar chart: alerts raised by rule",
      desc: "One bar for each rule that raised an alert in the period; the longest bar is the rule that raised most.",
    },
    outcome: {
      id: "am-closed-by-outcome",
      heading: "Closed by outcome",
      caption: "Alerts closed by outcome",
      columns: ["Outcome", "Alerts closed"],
      title: "Bar chart: alerts closed by outcome",
      desc: "One bar for each outcome an alert was closed with in the period; the longest bar is the commonest outcome.",
    },
    time: {
      id: "am-time-to-close",
      heading: "Time to close",
      caption: "Alerts closed by time taken",
      columns: ["Time taken", "Alerts closed"],
      title: "Bar chart: alerts closed by time taken",
      desc: "One bar for each length of time an alert took to close; the longest bar is the commonest.",
    },
  },
  open: {
    id: "am-open-alerts",
    heading: "Alerts",
    says: (n: number): string => `${plural(n, "alert")} open`,
    caption: "Open alerts by source and age",
    columns: ["Source", "Under a day", "1 to 7 days", "7 to 30 days", "Over 30 days"],
  },
  hotlist: { id: "am-hotlist-matches", heading: "Hotlist matches", says: (n: number): string => `${plural(n, "match", "matches")} in the period` },
  team: {
    id: "am-team-view",
    heading: "Team view",
    caption: "Team view by rule",
    columns: ["Rule", "Unassigned", "Mine", "Older than 7 days", "Closed as not of interest"],
    noneClosed: "none closed",
  },
  held: {
    id: "am-held-rows",
    heading: "Held rows",
    caption: "Held rows by what became of them",
    columns: ["What became of them", "Rows"],
    rows: ["Held", "Released", "Rejected"],
  },
  limit: {
    title: "This report is too large to draw",
    would: (n: number, what: "alerts" | "customers", cap: number): string => `This report would count ${formatNumber(n)} ${what}, past its limit of ${formatNumber(cap)}.`,
    choose: "Choose a shorter period.",
    shortest: "This is the shortest period.",
    // The customers' bound counts every verifying document the reader can see, with no date (`_customers`), so no period clears it.
    notByPeriod: "A shorter period does not change this limit.",
  },
  notFound: { title: "Case not found", message: "This case is not one you can open." },
  unreadable: {
    title: "The figures could not be read",
    message: "The figures could not be read just now. Nothing has changed. Try again in a few minutes.",
  },
} as const;

// -------------------------------------------------------------------------------------------------- what the route sends

interface Count {
  week_start: string;
  label: string;
  typology: string;
  count: number;
}

/** The four age bands of `open_by_source`, in the order of the table's columns (`AgeBand` in `schemas/domain.py`). */
const AGE_BANDS = ["under a day", "1 to 7 days", "7 to 30 days", "over 30 days"] as const;
type Age = (typeof AGE_BANDS)[number];

interface OpenCount {
  label: string;
  typology: string;
  age: Age;
  count: number;
}

interface Team {
  label: string;
  typology: string;
  unassigned: number;
  mine: number;
  older: number;
  closed: number;
  notOfInterest: number;
}

/** What the report route sent that the page draws, checked: the same names as the Conduit's `ReportFigures`. */
export interface Report {
  weeks: number;
  asOf: string;
  /** The alerts raised in the period, of every kind: the sum of the rows of `raised_by_rule`, never the route's `alerts_total` (typology alerts alone). */
  total: number;
  raised: Count[];
  closed: Count[];
  took: { label: string; value: number }[];
  hotlists: number;
  /** The alerts still open, by rule group and age band, as the route counted them for this reader (whenever they were raised). */
  open: OpenCount[];
  team: Team[];
  held: { held: number; released: number; rejected: number } | null;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isCount = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && Number.isInteger(value) && value >= 0;
const isText = (value: unknown): value is string => typeof value === "string";

/** A list the route always sends: an absent one is not an empty one, and is not read as one (the owner's ruling of 25 November 2026). */
function listOf<T>(value: unknown, read: (item: unknown) => T | undefined): T[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: T[] = [];
  for (const item of value) {
    const checked = read(item);
    if (checked === undefined) return undefined;
    out.push(checked);
  }
  return out;
}

// Every field of a row is required, a default included: the route serialises the whole model (`typology` is `""` where there is none, a
// count is `0`), and `packages/schemas/generated/ReportFigures.ts` marks them optional only because the model gives them a default.
// A row with a field missing is not the route's row, so it is never read with a zero or an empty word put in its place.

const weekCount = (item: unknown): Count | undefined =>
  isRecord(item) && isText(item["week_start"]) && isText(item["label"]) && isText(item["typology"]) && isCount(item["count"])
    ? { week_start: item["week_start"], label: item["label"], typology: item["typology"], count: item["count"] }
    : undefined;

const openCount = (item: unknown): OpenCount | undefined =>
  isRecord(item) && isText(item["label"]) && isText(item["typology"]) && (AGE_BANDS as readonly unknown[]).includes(item["age"]) && isCount(item["count"])
    ? { label: item["label"], typology: item["typology"], age: item["age"] as Age, count: item["count"] }
    : undefined;

function teamRow(item: unknown): Team | undefined {
  if (!isRecord(item) || !isText(item["label"]) || !isText(item["typology"])) return undefined;
  const { unassigned, mine, older_than_week: older, closed, not_of_interest: notOfInterest } = item;
  if (!isCount(unassigned) || !isCount(mine) || !isCount(older) || !isCount(closed) || !isCount(notOfInterest)) return undefined;
  return { label: item["label"], typology: item["typology"], unassigned, mine, older, closed, notOfInterest };
}

/**
 * The route's figures, or `undefined` when the body is anything but them: a partial figure is never made from what could be read, and a
 * field the route always sends but this body lacks is "could not be read", never a zero (the owner's ruling of 25 November 2026, from
 * the finding that `{"alerts_total": 3, "monitoring": {}}` was drawn as "0 alerts raised"). Required: `period_weeks`, `as_of`,
 * `generated_at`, `alerts_total`, `monitoring` with each of its six lists, and `held` (an object, or `null` where the route sends none).
 * `alerts_total` is checked and not drawn: the route counts typology alerts alone in it ("as they always have", `schemas/domain.py`), and
 * the page's count of alerts raised is that of `monitoring.raised_by_rule`, which counts every kind, as the React board's is.
 */
export function readReport(body: unknown): Report | undefined {
  if (!isRecord(body) || !isCount(body["alerts_total"]) || !isRecord(body["monitoring"])) return undefined;
  const period = body["period_weeks"];
  if (!isCount(period) || period < 1 || period > 52 || !isText(body["as_of"]) || !isText(body["generated_at"])) return undefined;
  const monitoring = body["monitoring"];
  const raised = listOf(monitoring["raised_by_rule"], weekCount);
  const closed = listOf(monitoring["closed_by_outcome"], weekCount);
  const hotlists = listOf(monitoring["hotlist_matches"], weekCount);
  const took = listOf(monitoring["time_to_close"], (item) => (isRecord(item) && isText(item["label"]) && isCount(item["value"]) ? { label: item["label"], value: item["value"] } : undefined));
  const team = listOf(monitoring["team"], teamRow);
  const open = listOf(monitoring["open_by_source"], openCount);
  if (!raised || !closed || !hotlists || !took || !team || !open) return undefined;
  let held: Report["held"] = null;
  const sent = body["held"];
  if (sent === undefined) return undefined;
  if (sent !== null) {
    if (!isRecord(sent) || !isCount(sent["held"]) || !isCount(sent["released"]) || !isCount(sent["rejected"])) return undefined;
    held = { held: sent["held"], released: sent["released"], rejected: sent["rejected"] };
  }
  return {
    weeks: period,
    asOf: body["as_of"],
    total: raised.reduce((n, row) => n + row.count, 0),
    raised,
    closed,
    took,
    hotlists: hotlists.reduce((n, row) => n + row.count, 0),
    open,
    team,
    held,
  };
}

export interface Limit {
  what: "alerts" | "customers";
  cap: number;
  wouldBe: number;
}

/** The route's 409, or `undefined` when the body is not one. */
export function readLimit(body: unknown): Limit | undefined {
  if (!isRecord(body) || body["error"] !== "limit_exceeded") return undefined;
  const kind = body["cap_kind"];
  if ((kind !== "alerts" && kind !== "customers") || !isCount(body["cap"]) || !isCount(body["would_be"])) return undefined;
  return { what: kind, cap: body["cap"], wouldBe: body["would_be"] };
}

// -------------------------------------------------------------------------------------------------- what the page draws

export interface Bar {
  label: string;
  value: string;
  width: number;
  y: number;
  labelY: number;
  valueX: number;
  textY: number;
}

export interface Chart {
  title: string;
  desc: string;
  viewBox: string;
  bars: Bar[];
}

export interface TableRow {
  head: string;
  cells: string[];
}

export interface Figure {
  id: string;
  heading: string;
  caption: string;
  columns: readonly string[];
  rows: TableRow[];
  /** The chart that comes before the table; absent for a table that is not a chart. */
  chart: Chart | null;
  /** Said instead of a chart and a table when there is nothing to count. */
  empty: string | null;
  /** A sentence under the heading (the hotlist matches). */
  says: string | null;
}

export interface Period {
  weeks: number;
  text: string;
  href: string | null;
}

export type MonitoringView =
  | { kind: "figures"; headline: string; countedOn: string | null; periods: Period[]; nothing: string | null; figures: Figure[] }
  | { kind: "limit"; sentence: string; periods: Period[] };

/** `/reports?case=…&weeks=…`: the case is encoded as one piece. */
export const periodHref = (caseId: string, weeks: number): string => `/reports?case=${encodeURIComponent(caseId)}&weeks=${weeks}`;

/** A period asked for: one of the four, or the default. */
export function periodOf(asked: string | undefined): number {
  const weeks = Number(asked);
  return (PERIODS as readonly number[]).includes(weeks) && /^\d+$/.test(asked ?? "") ? weeks : DEFAULT_PERIOD;
}

function periodsFor(caseId: string, current: number, only: (weeks: number) => boolean): Period[] {
  return PERIODS.filter(only).map((weeks) => ({ weeks, text: ALERT_MONITORING_WORDS.periodLink(weeks), href: weeks === current ? null : periodHref(caseId, weeks) }));
}

/** The chart of a figure's rows: one bar for each, the largest `WIDEST` wide and the others in proportion to it. */
export function chartOf(words: { title: string; desc: string }, rows: { label: string; count: number }[]): Chart {
  const most = Math.max(1, ...rows.map((row) => row.count));
  const bars = rows.map((row, i): Bar => {
    const width = Math.round((row.count / most) * WIDEST);
    const y = 4 + i * ROW_HEIGHT;
    return { label: row.label, value: formatNumber(row.count), width, y, labelY: y + TEXT_DROP, valueX: BAR_LEFT + width + 6, textY: y + TEXT_DROP };
  });
  return {
    title: words.title,
    desc: `${words.desc} ${ALERT_MONITORING_WORDS.tableFollows}`,
    viewBox: `0 0 ${VIEW_WIDTH} ${rows.length * ROW_HEIGHT + 8}`,
    bars,
  };
}

function figureOf(words: { id: string; heading: string; caption: string; columns: readonly string[]; title: string; desc: string }, rows: { label: string; count: number }[], none: string): Figure {
  const empty = rows.every((row) => row.count === 0);
  return {
    id: words.id,
    heading: words.heading,
    caption: words.caption,
    columns: words.columns,
    rows: empty ? [] : rows.map((row) => ({ head: row.label, cells: [formatNumber(row.count)] })),
    chart: empty ? null : chartOf(words, rows),
    empty: empty ? none : null,
    says: null,
  };
}

const RANK: Record<string, number> = { typology: 0, hotlists: 1, monitors: 2 };
const rankOf = (label: string): number => RANK[label] ?? 3;

/** The report as a page: sections in the React board's order, each figure the sum of rows the route sent. */
export function monitoringView(report: Report, caseId: string): MonitoringView {
  const words = ALERT_MONITORING_WORDS;
  const headline = words.raised(report.total, report.weeks);
  const countedOn = !Number.isNaN(new Date(report.asOf).getTime()) ? words.countedOn(formatDay(report.asOf)) : null;
  const periods = periodsFor(caseId, report.weeks, () => true);
  // The period bounds what was RAISED in it and nothing else: the route counts a closure by when it was decided and the team view over
  // every alert the reader may see (`services/api/reports.py` `_monitoring_figures`, `_panel_figures`), and sends the held rows to
  // Editors whatever the period holds. With nothing raised, the two sections of what was raised are said once in words and every other
  // figure the route sent is still drawn (a round-4 finding: a page that said only this hid figures the route had sent).
  const nothing = report.total === 0 ? words.noAlerts : null;
  const weeks = new Map<string, number>();
  for (const row of report.raised) weeks.set(row.week_start, (weeks.get(row.week_start) ?? 0) + row.count);
  const week = [...weeks].sort(([a], [b]) => a.localeCompare(b)).map(([start, count]) => ({ label: formatDay(start), count }));

  const groups = new Map<string, { label: string; typology: string; count: number }>();
  for (const row of report.raised) {
    const key = `${row.label}:${row.typology}`;
    const seen = groups.get(key) ?? { label: row.label, typology: row.typology, count: 0 };
    seen.count += row.count;
    groups.set(key, seen);
  }
  const byRule = [...groups.values()]
    .sort((a, b) => rankOf(a.label) - rankOf(b.label) || a.typology.localeCompare(b.typology) || a.label.localeCompare(b.label))
    .map((g) => ({ label: groupName(g.label, g.typology), count: g.count }));

  const outcomes = new Map<string, number>();
  for (const row of report.closed) outcomes.set(row.label, (outcomes.get(row.label) ?? 0) + row.count);
  const outcome = [...outcomes].map(([label, count]) => ({ label: closingReasonLabel(label === "closed" ? null : label) || "Closed, no outcome", count }));

  const time = report.took.map((row) => ({ label: row.label.charAt(0).toUpperCase() + row.label.slice(1), count: row.value }));

  // The open alerts, as the board's *Alerts* panel draws them: the count in words and a table of source by age, groups in the order the
  // route sent them, a cell the sum of the rows the route sent for it. Drawn whatever the period holds (the route counts them over every
  // alert the reader may see, `_panel_figures`); with none open, the count alone, as the board does.
  const sources = [...new Map(report.open.map((c) => [`${c.label}:${c.typology}`, c])).values()];
  const cell = (key: string, age: Age): number => report.open.filter((c) => `${c.label}:${c.typology}` === key && c.age === age).reduce((n, c) => n + c.count, 0);
  const openRows = sources.map((c): TableRow => ({ head: groupName(c.label, c.typology), cells: AGE_BANDS.map((age) => formatNumber(cell(`${c.label}:${c.typology}`, age))) }));
  const openTotal = report.open.reduce((n, c) => n + c.count, 0);

  const figures: Figure[] = [
    {
      id: words.open.id,
      heading: words.open.heading,
      caption: words.open.caption,
      columns: words.open.columns,
      rows: openRows,
      chart: null,
      empty: null,
      says: words.open.says(openTotal),
    },
    ...(nothing === null ? [figureOf(words.bars.week, week, words.noAlerts), figureOf(words.bars.rule, byRule, words.noAlerts)] : []),
    figureOf(words.bars.outcome, outcome, words.noClosed),
    figureOf(words.bars.time, time, words.noClosed),
    { id: words.hotlist.id, heading: words.hotlist.heading, caption: "", columns: [], rows: [], chart: null, empty: null, says: words.hotlist.says(report.hotlists) },
  ];
  if (report.team.length > 0) {
    const team = [...report.team]
      .sort((a, b) => rankOf(a.label) - rankOf(b.label) || a.typology.localeCompare(b.typology) || a.label.localeCompare(b.label))
      .map((t): TableRow => ({
        head: groupName(t.label, t.typology),
        cells: [
          formatNumber(t.unassigned),
          formatNumber(t.mine),
          formatNumber(t.older),
          t.closed === 0 ? words.team.noneClosed : `${Math.round((t.notOfInterest / t.closed) * 100)}% of ${formatNumber(t.closed)}`,
        ],
      }));
    figures.push({ id: words.team.id, heading: words.team.heading, caption: words.team.caption, columns: words.team.columns, rows: team, chart: null, empty: null, says: null });
  }
  // Only when the route sent them: for a Viewer it sends none, and nothing here says there are any.
  if (report.held !== null) {
    const h = report.held;
    figures.push({
      id: words.held.id,
      heading: words.held.heading,
      caption: words.held.caption,
      columns: words.held.columns,
      rows: [h.held, h.released, h.rejected].map((n, i): TableRow => ({ head: words.held.rows[i] as string, cells: [formatNumber(n)] })),
      chart: null,
      empty: null,
      says: null,
    });
  }
  return { kind: "figures", headline, countedOn, periods, nothing, figures };
}

/**
 * A report past its bound, in words: the numbers are the route's. The alerts' bound moves with the period, so its way out is a link to each
 * shorter period; the customers' bound does not (it counts every verifying document the reader can see, with no date), so for it the page
 * offers no link that would answer the same and says so.
 */
export function limitView(limit: Limit, caseId: string, current: number): MonitoringView {
  const words = ALERT_MONITORING_WORDS.limit;
  const sentence = words.would(limit.wouldBe, limit.what, limit.cap);
  if (limit.what === "customers") return { kind: "limit", sentence: `${sentence} ${words.notByPeriod}`, periods: [] };
  const periods = periodsFor(caseId, current, (weeks) => weeks < current);
  return { kind: "limit", sentence: `${sentence} ${periods.length > 0 ? words.choose : words.shortest}`, periods };
}
