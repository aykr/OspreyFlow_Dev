// Verify's would-be alerts (`06_DECISIONS.md` ADR-133 decision 6, stage (d)): beside the rejection
// report, what the pipeline's checks on load would raise over the sample — judged as at the load,
// each rule as its author, over the rows the person verifying may read in full — and each check a
// dry run cannot judge, with why. Nothing was raised, held or written.
import type { VerifyReport } from "../../../../../packages/schemas/generated";
const ON_HIT_WORDS: Record<string, string> = { alert: "would load with an alert", hold: "would hold its rows for review" };

/** The would-be alerts and the checks a dry run could not judge, in words; nothing was written. */
export function WouldRaisePanel({ report }: { report: VerifyReport }) {
  const raised = report.would_raise ?? [];
  const notJudged = report.checks_not_judged ?? [];
  const judged = report.checks_judged ?? 0;
  return (
    <div style={{ display: "grid", gap: "var(--sp-8)" }}>
      <p className="label" style={{ margin: 0 }}>
        {judged === 0 && notJudged.length === 0
          ? "No rule checks this pipeline's loads. Attach rules in Checks on load."
          : `${judged} check(s) judged the rows you may read in full, as they would at the load. Nothing was raised, held or written.`}
      </p>
      {raised.length > 0 ? (
        <ul aria-label="Alerts this sample would raise" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
          {raised.map((w) => (
            <li key={`${w.rule_id}:${w.entity_id}`}>
              <strong>{w.rule_name}</strong>
              {` · ${w.severity} severity · ${w.entity_name} (${w.entity_type}) ${ON_HIT_WORDS[w.on_hit] ?? ""}`}
            </li>
          ))}
        </ul>
      ) : (
        judged > 0 && <p className="label" style={{ margin: 0 }}>The sample would raise no alert.</p>
      )}
      {notJudged.length > 0 && (
        <ul aria-label="Checks a dry run cannot judge" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
          {notJudged.map((n) => (
            <li key={n.rule_id} className="label">
              <strong>{n.rule_name}</strong>: {n.why}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
