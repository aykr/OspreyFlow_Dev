// The words a pack and a trend are described in, shared by the screens and the print document so
// the two never say different things (ADR-113 stage 5). Pure: no DOM, no fetch.
import type { PackItem, TrendFigures } from "../../../../packages/schemas/generated";

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

/** How many items are withheld, said once, never which. */
export function withheldSentence(n: number): string {
  return `${plural(n, "item")} in this pack ${n === 1 ? "is" : "are"} withheld from you.`;
}

export const KIND_LABEL: Record<PackItem["kind"], string> = {
  trend: "Trend",
  assessment: "Assessment",
  entity: "Entity",
  note: "Note",
};

/** The name an item goes by in an accessible label — a short title, never a truncated datum. */
export function itemShortTitle(item: PackItem): string {
  if (item.kind === "trend") return item.trend?.definition.title ?? "Trend";
  if (item.kind === "assessment") return item.assessment?.statement ?? "Assessment";
  if (item.kind === "entity") return item.entity?.name ?? "Entity";
  const text = item.note ?? "";
  return text.length > 60 ? `${text.slice(0, 60)}…` : text;
}

/** "Sum of amount: 12,400 over 31 events in 12 weeks; 2 events had no amount and are not in the sum". */
export function trendSentence(figures: TrendFigures): string {
  const { definition, result } = figures;
  const weeks = plural(definition.weeks ?? 12, "week");
  const events = plural(result.events, "event");
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

/** The distinct periods, in order — every one, never a sample. */
export function periodsOf(figures: TrendFigures): string[] {
  return [...new Set(figures.result.points.map((p) => p.period_start))].sort();
}
