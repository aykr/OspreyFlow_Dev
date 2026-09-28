export interface HistogramBucket {
  key: string;
  count: number;
  label: string;
}

export interface HistogramProps {
  buckets: HistogramBucket[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

/** The cross-filter histogram pattern (`spec/02_GLASS_FRONTEND.md` §2's
 * "A histogram bar click filters everything") — Phase 5 wires the actual
 * cross-filter; this checkpoint ships the interactive primitive itself. */
export function Histogram({ buckets, selectedKey, onSelect }: HistogramProps) {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  return (
    <div className="histogram" role="group">
      {buckets.map((bucket) => (
        <button
          key={bucket.key}
          type="button"
          className="histogram__bar"
          aria-pressed={bucket.key === selectedKey}
          aria-label={`${bucket.label}: ${bucket.count}`}
          style={{ height: `${(bucket.count / max) * 100}%`, border: "none" }}
          onClick={() => onSelect(bucket.key)}
        />
      ))}
    </div>
  );
}
