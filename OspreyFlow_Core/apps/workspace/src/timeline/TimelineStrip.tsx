// The folded timeline's row (ADR-115 E4; DESIGN.md §5a, the reference): a small density strip on
// the data ramp and the date range in mono, from the histogram the open timeline draws.
import { useTimelineSummary } from "./timelineSummary";

const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : "");

export function TimelineStrip() {
  const histogram = useTimelineSummary();
  if (!histogram || histogram.bucketing !== "fixed_interval" || histogram.buckets.length === 0) return null;
  const buckets = histogram.buckets;
  const tallest = Math.max(1, ...buckets.map((b) => b.count));
  const first = day(buckets[0]!.start);
  const last = day(buckets[buckets.length - 1]!.start);
  return (
    <span className="timeline-strip">
      <span className="timeline-strip__bars" aria-hidden="true">
        {buckets.map((b, i) => (
          <span key={i} className="timeline-strip__bar" style={{ height: `${Math.round((b.count / tallest) * 100)}%` }} />
        ))}
      </span>
      <span className="value timeline-strip__range">{first === last ? first : `${first} to ${last}`}</span>
    </span>
  );
}
