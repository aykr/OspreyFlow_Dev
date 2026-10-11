// A trend drawn (ADR-113 stage 5): the sentence first, then one bar for every period — stacked by
// series when there are series — and a legend naming every series. Nothing is sampled or capped
// (rule 2): a trend too large to draw is refused by the server with its choices, not sliced here.
import type { TrendFigures } from "../../../../packages/schemas/generated";
import { formatDay, formatNumber, periodsOf, trendSentence } from "./packText";

export const CHANNELS = ["--ch-azure", "--ch-ochre", "--ch-jade", "--ch-plum", "--ch-rose", "--ch-cyan", "--ch-indigo", "--ch-moss"];

export function TrendChart({ figures }: { figures: TrendFigures }) {
  const { result, definition } = figures;
  const periods = periodsOf(figures);
  const series = result.series ?? [];
  const colourOf = (name: string | null | undefined): string => {
    const at = name == null ? -1 : series.indexOf(name);
    return at < 0 ? "--brass" : (CHANNELS[at % CHANNELS.length] ?? "--brass");
  };
  const totals = periods.map((period) =>
    result.points.filter((p) => p.period_start === period).reduce((sum, p) => sum + Math.max(0, p.value), 0),
  );
  const most = Math.max(1, ...totals);
  const unit = result.interval === "month" ? "month" : "week";

  return (
    <div style={{ display: "grid", gap: "var(--sp-8)" }}>
      <p className="value" style={{ margin: 0 }}>{trendSentence(figures)}</p>
      {periods.length === 0 ? (
        <p className="label" style={{ margin: 0 }}>No events fell in this period.</p>
      ) : (
        <>
          <div
            role="img"
            aria-label={`${definition.title}: one bar for each of ${periods.length} ${unit === "month" ? "months" : "weeks"}, from ${formatDay(periods[0] ?? "")} to ${formatDay(periods[periods.length - 1] ?? "")}`}
            style={{ display: "flex", alignItems: "flex-end", gap: "var(--sp-4)", height: 140 }}
          >
            {periods.map((period, i) => {
              const here = result.points.filter((p) => p.period_start === period);
              return (
                <div
                  key={period}
                  data-period={period}
                  title={`${unit === "month" ? "Month" : "Week"} of ${formatDay(period)}: ${formatNumber(totals[i] ?? 0)}`}
                  style={{ flex: 1, minWidth: 1, display: "flex", flexDirection: "column-reverse", height: `${((totals[i] ?? 0) / most) * 100}%`, minHeight: totals[i] ? 2 : 0 }}
                >
                  {here.map((p, at) => (
                    <span key={`${p.series ?? ""}-${at}`} style={{ flex: Math.max(0, p.value), background: `var(${colourOf(p.series)})` }} />
                  ))}
                </div>
              );
            })}
          </div>
          <p className="label" style={{ margin: 0 }}>{`From ${formatDay(periods[0] ?? "")} to ${formatDay(periods[periods.length - 1] ?? "")}; the tallest bar is ${formatNumber(most)}.`}</p>
        </>
      )}
      {series.length > 0 && (
        <ul aria-label="Series legend"style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: "var(--sp-12)" }}>
          {series.map((name) => (
            <li key={name} className="label" style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
              <span aria-hidden style={{ width: 10, height: 10, background: `var(${colourOf(name)})` }} />
              {name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
