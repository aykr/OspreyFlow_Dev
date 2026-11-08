// The case's *Figures* (ADR-145 Amendment 4 decision 8, replacing ADR-111's Reports view): a way of
// looking at a case, beside Graph and Map, for people who read rather than investigate. Every figure
// arrives counted for this reader by the Conduit (rule 3); the view only draws it — in words first,
// and in plain bars built from the design tokens. Held rows appear only when the server sends them
// (Editors and above). Its *Alerts* panel (ADR-146 decision 9) and its *Drawing* panel (drawn,
// promoted, awaiting review, withdrawn; served once promotions exist, L3.4) sit with the rest.
// Opened from an alert (the Reports Viewer's journey, decision 10), it says so, outlines the
// panel the alert concerns, and offers the way back.
import { useEffect, useRef, useState } from "react";

import type { OutcomeCount, PoleFigures, ReportFigures } from "../../../../packages/schemas/generated";

type DrawingFigures = NonNullable<ReportFigures["drawing"]>;
import { CLOSING_REASONS, type ClosingReason } from "../alerts/closingReasons";
import { typologyLabel } from "../alerts/names";
import { utcStampOf } from "../time/utcStamp";
import { Button, Select } from "../design/primitives";
import { AlertsPanel } from "./AlertsPanel";
import { fetchFeedCsv, fetchReport, type ReportsApi } from "./api";
import { Bars, channel, NUMBER, plural, Section } from "./figureParts";

export const PERIODS = [4, 12, 26, 52];
/** The Outcomes table's columns: open, claimed, each closing reason as the close dialog says it
 * (ADR-133 Amendment 5), and closed with none (taken back). Build order step 18c (D12). */
type OutcomeField = "open" | "claimed" | ClosingReason | "closed";
const OUTCOME_COLUMNS: ReadonlyArray<readonly [OutcomeField, string]> = [
  ["open", "Open"],
  ["claimed", "Claimed"],
  ...(Object.entries(CLOSING_REASONS) as Array<[ClosingReason, string]>),
  ["closed", "Closed, no outcome"],
];

const POLE_CLASS_LABELS: Record<string, string> = {
  person: "Person",
  object: "Object",
  location: "Location",
  event: "Event",
  organisation: "Organisation",
};

/** One line per type under its class, the class's own total on the line above (ADR-126 decision 4). */
function PoleLine({ label, total, types }: { label: string; total: number; types: { entity_type: string; count: number }[] }) {
  const line = `${label}: ${NUMBER.format(total)}`;
  return (
    <li aria-label={line} style={{ display: "grid", gap: "var(--sp-4)" }}>
      <span className="value">{line}</span>
      {types.length > 0 && (
        <ul style={{ listStyle: "none", margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" }}>
          {types.map((t) => (
            <li key={t.entity_type} className="label">{`${t.entity_type}: ${NUMBER.format(t.count)}`}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** The POLE summary (ADR-126 decision 4): the case's records by POLE class and type, as the reader
 * sees them, before resolution and not for the period. */
function PoleCard({ pole }: { pole: PoleFigures }) {
  const other = pole.other ?? [];
  return (
    <Section title="POLE summary">
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-8)" }}>
        {(pole.classes ?? []).map((c) => (
          <PoleLine key={c.pole_class} label={POLE_CLASS_LABELS[c.pole_class] ?? c.pole_class} total={c.total} types={c.types ?? []} />
        ))}
        {other.length > 0 && (
          <PoleLine label="Other (not in this ontology)" total={other.reduce((n, t) => n + t.count, 0)} types={other} />
        )}
      </ul>
      <p className="value" style={{ margin: 0 }}>{`Links: ${NUMBER.format(pole.links)}`}</p>
      <p className="label" style={{ margin: 0 }}>
        {`Records before resolution, counted at ${utcStampOf(pole.counted_at)}; not for the period.`}
      </p>
    </Section>
  );
}

function RaisedByWeek({ figures, colours }: { figures: ReportFigures; colours: Map<string, string> }) {
  const weeks = [...new Set((figures.alerts_by_week ?? []).map((w) => w.week_start))].sort();
  const totals = weeks.map((week) => (figures.alerts_by_week ?? []).filter((w) => w.week_start === week).reduce((n, w) => n + w.count, 0));
  const most = Math.max(1, ...totals);
  if (weeks.length === 0) return <p className="label" style={{ margin: 0 }}>No alerts were raised in this period.</p>;
  return (
    <>
      <div role="img" aria-label="Alerts raised each week, by typology" style={{ display: "flex", alignItems: "flex-end", gap: "var(--sp-4)", height: 120 }}>
        {weeks.map((week, i) => (
          <div key={week} title={`Week of ${week}: ${totals[i]}`} style={{ flex: 1, display: "flex", flexDirection: "column-reverse", height: `${((totals[i] ?? 0) / most) * 100}%` }}>
            {(figures.alerts_by_week ?? []).filter((w) => w.week_start === week).map((w) => (
              <span key={w.typology} style={{ flex: w.count, background: `var(${colours.get(w.typology) ?? "--brass"})` }} />
            ))}
          </div>
        ))}
      </div>
      <ul aria-label="Typologies" style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: "var(--sp-12)" }}>
        {[...colours.entries()].map(([typology, colour]) => (
          <li key={typology} className="label" style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
            <span aria-hidden style={{ width: 10, height: 10, background: `var(${colour})` }} />
            {typologyLabel(typology)}
          </li>
        ))}
      </ul>
    </>
  );
}

/** Where the Figures were opened from: an alert on the Reports Viewer's Home (ADR-145 Amendment 4
 * decision 10), named in words, with the way back. */
export interface FromAlert {
  words: string;
  onBack: () => void;
}

function DrawingCard({ drawing }: { drawing: DrawingFigures }) {
  return (
    <Section title="Drawing">
      <Bars label="Drawing figures" rows={[
        { label: "Drawn", value: drawing.drawn, colour: channel(0) },
        { label: "Promoted", value: drawing.promoted, colour: channel(1) },
        { label: "Awaiting review", value: drawing.awaiting_review, colour: channel(2) },
        { label: "Withdrawn", value: drawing.withdrawn, colour: channel(3) },
      ]} />
    </Section>
  );
}

export interface ReportsViewProps extends ReportsApi {
  canDownload: boolean;
  /** Opens an alert at its address; only for a reader Rules and Monitoring is offered to. */
  onOpenAlert?: (alertId: string) => void;
  fromAlert?: FromAlert | null;
  /** The period to open on (the journey's, from the alert's age); 12 weeks when left out. */
  initialWeeks?: number;
}

export function ReportsView({ canDownload, onOpenAlert, fromAlert = null, initialWeeks = 12, ...api }: ReportsViewProps) {
  const [weeks, setWeeks] = useState(PERIODS.includes(initialWeeks) ? initialWeeks : 12);
  const back = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (fromAlert) back.current?.focus();
  }, [fromAlert]);
  const [figures, setFigures] = useState<ReportFigures | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setProblem(null);
    fetchReport(api, weeks)
      .then((found) => !cancelled && setFigures(found))
      .catch((e: Error) => {
        if (!cancelled) {
          setFigures(null);
          setProblem(e.message);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId, weeks]);

  async function download() {
    try {
      const blob = await fetchFeedCsv(api, weeks);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `case-report-${weeks}-weeks.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setProblem((e as Error).message);
    }
  }

  const typologies = [...new Set((figures?.outcomes ?? []).map((o) => o.typology))];
  const colours = new Map(typologies.map((t, i) => [t, channel(i)]));

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
      {fromAlert && (
        <div role="note" aria-label="Opened from an alert" className="label"
             style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
          <span>{`From ${fromAlert.words}`}</span>
          <span aria-hidden>·</span>
          <button ref={back} type="button" className="btn" onClick={fromAlert.onBack}>← Back to your alerts</button>
        </div>
      )}
      <header style={{ display: "flex", gap: "var(--sp-12)", alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Figures</h2>
        <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          Period
          <Select aria-label="Period" value={String(weeks)} onChange={(e) => setWeeks(Number(e.target.value))}>
            {PERIODS.map((p) => (
              <option key={p} value={p}>{`Last ${p} weeks`}</option>
            ))}
          </Select>
        </label>
        <span style={{ flex: 1 }} />
        {/* ADR-112: the feed is the Reports Viewer's right (R2); offered only to its holders. */}
        {canDownload && <Button onClick={() => void download()}>Download the figures (CSV)</Button>}
      </header>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      {!figures && !problem && <p className="label">Counting…</p>}
      {figures && (
        <>
          <p className="value" style={{ margin: 0 }}>
            {`${plural(figures.alerts_total, "alert")} in the last ${figures.period_weeks} weeks`}
          </p>
          <p className="label" style={{ margin: 0 }}>
            Counted for you: an alert concerning anything you cannot see is in no figure here.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(22rem, 1fr))", gap: "var(--sp-16)" }}>
            <AlertsPanel api={api} monitoring={figures.monitoring ?? null} onOpenAlert={onOpenAlert} outlined={fromAlert !== null} />
            <Section title="Alerts raised each week">
              <RaisedByWeek figures={figures} colours={colours} />
            </Section>
            <Section title="Open alerts by age">
              <Bars rows={(figures.open_by_age ?? []).map((c) => ({ label: c.label, value: c.value }))} />
            </Section>
            <Section title="Outcomes">
              <table className="table" aria-label="Outcomes by typology">
                <thead>
                  <tr>
                    <th>Typology</th>
                    {OUTCOME_COLUMNS.map(([, heading]) => (
                      <th key={heading} style={{ textAlign: "right" }}>
                        {heading}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(figures.outcomes ?? []).map((o) => (
                    <tr key={o.typology}>
                      <td>{typologyLabel(o.typology)}</td>
                      {OUTCOME_COLUMNS.map(([field, heading]) => (
                        <td key={heading} style={{ textAlign: "right" }}>
                          {NUMBER.format((o as OutcomeCount)[field] ?? 0)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
            {/* ADR-126: a case without `fibo` carries no KYC card; the POLE card is D4. */}
            {figures.kyc && (
              <Section title="Customers by KYC status">
                <p style={{ margin: 0 }}>
                  {`${plural(figures.kyc.customers, "customer")}: ${NUMBER.format(figures.kyc.verified)} verified, ${NUMBER.format(figures.kyc.unverified)} unverified`}
                </p>
                <Bars
                  rows={(figures.kyc.by_band ?? []).map((b) => ({
                    label: `${b.label} risk`,
                    value: b.value,
                    colour: b.label === "high" ? "--error" : b.label === "medium" ? "--warning" : "--success",
                  }))}
                />
              </Section>
            )}
            {figures.pole && <PoleCard pole={figures.pole} />}
            {/* ADR-145 Amendment 4 decision 8: none until promotions exist (L3.4); never a zero. */}
            {figures.drawing && <DrawingCard drawing={figures.drawing} />}
            {figures.held && (
              <Section title="Held rows">
                <p style={{ margin: 0 }}>
                  {`${NUMBER.format(figures.held.held)} waiting for a reviewer · ${NUMBER.format(figures.held.released)} released · ${NUMBER.format(figures.held.rejected)} rejected`}
                </p>
              </Section>
            )}
          </div>
        </>
      )}
    </div>
  );
}
