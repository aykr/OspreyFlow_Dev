// The Reports view (`06_DECISIONS.md` ADR-111): a third way of looking at a case, beside Graph and
// Map, for people who read rather than investigate. Every figure arrives counted for this reader by
// the Conduit (rule 3); the view only draws it — in words first, and in plain bars built from the
// design tokens. Held rows appear only when the server sends them (Editors and above).
import { useEffect, useState } from "react";

import type { ReportFigures } from "../../../../packages/schemas/generated";
import { typologyLabel } from "../alerts/names";
import { Button, Select } from "../design/primitives";
import { fetchFeedCsv, fetchReport, type ReportsApi } from "./api";

const PERIODS = [4, 12, 26, 52];
const CHANNELS = ["--ch-azure", "--ch-ochre", "--ch-jade", "--ch-plum", "--ch-rose", "--ch-cyan", "--ch-indigo", "--ch-moss"];
const NUMBER = new Intl.NumberFormat("en-GB");

function plural(n: number, one: string, many = `${one}s`): string {
  return `${NUMBER.format(n)} ${n === 1 ? one : many}`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      aria-label={title}
      style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-8)", alignContent: "start" }}
    >
      <h3 className="value" style={{ margin: 0 }}>{title}</h3>
      {children}
    </section>
  );
}

/** One horizontal bar per row, its length the share of the largest; the number always written. */
function Bars({ rows }: { rows: { label: string; value: number; colour?: string }[] }) {
  const most = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
      {rows.map((r) => (
        <li key={r.label} style={{ display: "grid", gridTemplateColumns: "10rem 1fr", gap: "var(--sp-8)", alignItems: "center" }}>
          <span className="label">{`${r.label}: ${NUMBER.format(r.value)}`}</span>
          <span aria-hidden style={{ height: 10, width: `${(r.value / most) * 100}%`, minWidth: r.value ? 2 : 0,
                                     background: `var(${r.colour ?? "--brass"})` }} />
        </li>
      ))}
    </ul>
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

export function ReportsView(api: ReportsApi) {
  const [weeks, setWeeks] = useState(12);
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
  const colours = new Map(typologies.map((t, i) => [t, CHANNELS[i % CHANNELS.length] ?? "--brass"]));

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
      <header style={{ display: "flex", gap: "var(--sp-12)", alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Reports</h2>
        <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          Period
          <Select aria-label="Period" value={String(weeks)} onChange={(e) => setWeeks(Number(e.target.value))}>
            {PERIODS.map((p) => (
              <option key={p} value={p}>{`Last ${p} weeks`}</option>
            ))}
          </Select>
        </label>
        <span style={{ flex: 1 }} />
        <Button onClick={() => void download()}>Download the figures (CSV)</Button>
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
                    <th style={{ textAlign: "right" }}>Open</th>
                    <th style={{ textAlign: "right" }}>Claimed</th>
                    <th style={{ textAlign: "right" }}>True</th>
                    <th style={{ textAlign: "right" }}>False</th>
                  </tr>
                </thead>
                <tbody>
                  {(figures.outcomes ?? []).map((o) => (
                    <tr key={o.typology}>
                      <td>{typologyLabel(o.typology)}</td>
                      <td style={{ textAlign: "right" }}>{NUMBER.format(o.open ?? 0)}</td>
                      <td style={{ textAlign: "right" }}>{NUMBER.format(o.claimed ?? 0)}</td>
                      <td style={{ textAlign: "right" }}>{NUMBER.format(o.true_positive ?? 0)}</td>
                      <td style={{ textAlign: "right" }}>{NUMBER.format(o.false_positive ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
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
