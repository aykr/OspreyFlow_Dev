// How a link's dates read (ADR-127 decision 11). A link can be a span, and a span still running has
// no end: it reads "from …  (open)", never as a missing end or "present". Shared by the link panel,
// the edge overlay and the link's history, so one wording holds everywhere a link's dates show.

export interface IntervalLike {
  valid_from: string;
  valid_to?: string | null;
}

export function intervalText(interval: IntervalLike, options: { dateOnly?: boolean } = {}): string {
  const cut = (value: string): string => (options.dateOnly ? value.slice(0, 10) : value);
  if (interval.valid_to === null || interval.valid_to === undefined || interval.valid_to === "") {
    return `from ${cut(interval.valid_from)} (open)`;
  }
  return `${cut(interval.valid_from)} – ${cut(interval.valid_to)}`;
}
