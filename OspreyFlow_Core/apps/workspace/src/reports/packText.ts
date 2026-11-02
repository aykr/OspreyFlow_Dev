// The words a pack and a trend are described in, shared by the screens and the print document so
// the two never say different things (ADR-113 stage 5). Pure: no DOM, no fetch.
import type { AlertEntitySnapshot, AlertSnapshot, PackItem, TrendFigures } from "../../../../packages/schemas/generated";
import { closingReasonLabel } from "../alerts/closingReasons";

const NUMBER = new Intl.NumberFormat("en-GB");
const DAY = new Intl.DateTimeFormat("en-GB", { dateStyle: "long", timeZone: "UTC" });

export function formatNumber(n: number): string {
  return NUMBER.format(n);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${NUMBER.format(n)} ${n === 1 ? one : many}`;
}

/** "11 October 2026", whatever the zone of the reader; an unreadable value is shown as it came. */
export function formatDay(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : DAY.format(when);
}

/** That some of the pack's items are withheld from this reader, said once, with no number and never
 * which (ADR-124 decision 9). */
export const WITHHELD_ITEMS_SENTENCE = "Some items of this pack are withheld from you.";

export const KIND_LABEL: Record<PackItem["kind"], string> = {
  trend: "Trend",
  assessment: "Assessment",
  entity: "Entity",
  note: "Note",
  alert: "Alert",
};

/** The name an item goes by in an accessible label — a short title, never a truncated datum. */
export function itemShortTitle(item: PackItem): string {
  if (item.kind === "trend") return item.trend?.definition.title ?? "Trend";
  if (item.kind === "assessment") return item.assessment?.statement ?? "Assessment";
  if (item.kind === "entity") return item.entity?.name ?? "Entity";
  if (item.kind === "alert") return item.alert?.explanation ?? "Alert";
  const text = item.note ?? "";
  return text.length > 60 ? `${text.slice(0, 60)}…` : text;
}

/** "Sum of amount: 12,400 over 31 events in 12 weeks; 2 events had no amount and are not in the sum". */
export function trendSentence(figures: TrendFigures): string {
  const { definition, result } = figures;
  const weeks = plural(definition.weeks ?? 12, "week");
  // ADR-134 decision 3: an alert trend counts alerts.
  const events = plural(result.events, definition.source === "alerts" ? "alert" : "event");
  if (result.measure === "sum") {
    const field = definition.measure_field ?? "the chosen property";
    const unvalued = result.unvalued ?? 0;
    const missing =
      unvalued > 0
        ? `; ${plural(unvalued, "event")} had no ${field} and ${unvalued === 1 ? "is" : "are"} not in the sum`
        : "";
    return `Sum of ${field}: ${NUMBER.format(result.total)} over ${events} in ${weeks}${missing}`;
  }
  return `${events} in ${weeks}`;
}

/** The day a period starts on ("2026-09-14"), the key a point and its bar share; a value that is not
 * a time is kept as it came. */
export function periodKey(start: string): string {
  const when = new Date(start);
  return Number.isNaN(when.getTime()) ? start : when.toISOString().slice(0, 10);
}

/** The start of the Monday week or calendar month holding `when`, in UTC — the periods the
 * AnalyticsPort suite pins (`test_trend_counts_events_per_week`, `test_trend_counts_per_month`). */
function periodStart(when: Date, interval: TrendFigures["result"]["interval"]): Date {
  if (interval === "month") return new Date(Date.UTC(when.getUTCFullYear(), when.getUTCMonth(), 1));
  const day = new Date(Date.UTC(when.getUTCFullYear(), when.getUTCMonth(), when.getUTCDate()));
  day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
  return day;
}

/** Every period the trend's window touches, in order, the empty ones too — the port returns points
 * only where there were events, and an axis that skipped the empty ones would misstate time (ADR-113
 * Amendment 3, finding 4). A point outside the window is kept, never dropped. */
export function periodsOf(figures: TrendFigures): string[] {
  const keys = new Set(figures.result.points.map((p) => periodKey(p.period_start)));
  const from = new Date(figures.window_start);
  const to = new Date(figures.as_of);
  if (!Number.isNaN(from.getTime()) && !Number.isNaN(to.getTime())) {
    const interval = figures.result.interval;
    for (let at = periodStart(from, interval); at <= to; ) {
      keys.add(at.toISOString().slice(0, 10));
      if (interval === "month") at = new Date(Date.UTC(at.getUTCFullYear(), at.getUTCMonth() + 1, 1));
      else at = new Date(at.getTime() + 7 * 86_400_000);
    }
  }
  return [...keys].sort();
}

// --- an alert in a pack (ADR-134 decision 1) -------------------------------------------------------

const SEVERITY_WORD: Record<AlertSnapshot["severity"], string> = { high: "High", medium: "Medium", low: "Low" };
const KIND_WORD: Record<AlertSnapshot["kind"], string> = { typology: "Typology alert", hotlist: "Hotlist match", monitor: "Monitor match" };

/** "Typology alert (rapid_movement) · High severity · raised 29 September 2026". */
export function alertLine(alert: AlertSnapshot): string {
  const what = alert.typology ? `${KIND_WORD[alert.kind]} (${alert.typology})` : KIND_WORD[alert.kind];
  return `${what} · ${SEVERITY_WORD[alert.severity]} severity · raised ${formatDay(alert.raised_at)}`;
}

/** Where the alert stood when it was added: an open alert says it is open, a closed one its outcome
 * and the reason given. A snapshot, so it says "when this was added". */
export function alertStatusSentence(alert: AlertSnapshot): string {
  if (alert.status === "open") return "Open: not yet decided when this was added.";
  if (alert.status === "claimed") return "Open, being worked on, when this was added.";
  const reason = alert.reason ? `: ${alert.reason}` : "";
  if (alert.outcome) return `Closed as ${closingReasonLabel(alert.outcome)}${reason}.`;
  return `Closed without an outcome${reason}.`;
}

/** Rule 5: a match no person has confirmed is inferred, and the pack says so. */
/** One entity an alert matched: its name and type and, for a screening list's own entry
 * (`list_entry_on`, step 9e), whose entry it is — as the alert's detail says (`concernWords`). */
export function alertEntityWords(entity: AlertEntitySnapshot): string {
  return `${entity.name} (${entity.entity_type})${entity.list_entry_on ? ` · the entry on ${entity.list_entry_on}` : ""}`;
}

export function alertMatchSentence(alert: AlertSnapshot): string {
  return alert.match === "confirmed" ? "Confirmed by a person." : "Inferred: no one has confirmed this match.";
}

const MONEY = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });

/** Each piece of evidence as one line: a link it cites, or a transaction with its day and amount. */
export function alertEvidence(alert: AlertSnapshot): string[] {
  const links = (alert.links ?? []).map((l) => `${l.type.replace(/_/g, " ").toLowerCase()}: ${l.source_name} to ${l.target_name}`);
  const transactions = (alert.transactions ?? []).map(
    (t) => `${formatDay(t.occurred_at)}: ${t.source_name} to ${t.target_name}${t.amount != null ? `, ${MONEY.format(t.amount)}` : ""}`,
  );
  return [...links, ...transactions];
}
