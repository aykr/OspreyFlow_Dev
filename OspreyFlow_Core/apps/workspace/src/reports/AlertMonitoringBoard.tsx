// The *Alert monitoring* board (ADR-145 Amendment 4 decision 9, D2; ADR-134 decision 2): the
// monitoring figures the Conduit already serves with a case's report, drawn as a board on the
// Glass's *Dashboards*, first among the boards. Alerts raised per rule and week, closed by outcome,
// time to close, hotlist matches, and the team view (unassigned, mine, older than seven days, the
// share closed as not of interest), with the *Alerts* panel (ADR-146 decision 9).
//
// Every figure is the Conduit's, counted as the reader (rules 3 and 7); the board only adds up what
// it was given, filtered to a rule group and a period. *See the trend* in Rules and Monitoring and
// the Reports Viewer's *Open the dashboard* open it filtered to the alert's rule and period.
import { useEffect, useRef, useState } from "react";

import type { ReportFigures } from "../../../../packages/schemas/generated";
import { closingReasonLabel } from "../alerts/closingReasons";
import { Select } from "../design/primitives";
import { AlertsPanel } from "./AlertsPanel";
import { fetchReport, type ReportsApi } from "./api";
import { Bars, channel, groupKey, groupName, NUMBER, plural, Section, type RuleGroup } from "./figureParts";
import { PERIODS } from "./ReportsView";
import type { FromAlert } from "./ReportsView";

export const ALERT_MONITORING = { slug: "alert-monitoring", title: "Alert monitoring" } as const;

export interface BoardFilter {
  rule?: RuleGroup | null;
  weeks?: number;
}

export interface AlertMonitoringBoardProps {
  api: ReportsApi;
  filter?: BoardFilter;
  onOpenAlert?: (alertId: string) => void;
  fromAlert?: FromAlert | null;
}

const ALL = "";

/** Every rule group the figures name, in a fixed order (typologies by name, then hotlists, then
 * monitors), so a group keeps its colour whatever the filter. */
function groupsOf(figures: ReportFigures | null): RuleGroup[] {
  const m = figures?.monitoring;
  const seen = new Map<string, RuleGroup>();
  for (const g of [...(m?.raised_by_rule ?? []), ...(m?.open_by_source ?? []), ...(m?.team ?? [])]) {
    const group = { label: g.label, typology: g.typology ?? "" };
    seen.set(groupKey(group), group);
  }
  const rank = (g: RuleGroup) => (g.label === "typology" ? 0 : g.label === "hotlists" ? 1 : 2);
  return [...seen.values()].sort((a, b) => rank(a) - rank(b) || a.typology.localeCompare(b.typology));
}

/** The share closed as not of interest, said with how many were closed; "none closed" when none were. */
const share = (part: number, whole: number) =>
  whole === 0 ? "none closed" : `${Math.round((part / whole) * 100)}% of ${NUMBER.format(whole)}`;

export function AlertMonitoringBoard({ api, filter = {}, onOpenAlert, fromAlert = null }: AlertMonitoringBoardProps) {
  const [weeks, setWeeks] = useState(PERIODS.includes(filter.weeks ?? 12) ? (filter.weeks ?? 12) : 12);
  const [rule, setRule] = useState<string>(filter.rule ? groupKey(filter.rule) : ALL);
  const [figures, setFigures] = useState<ReportFigures | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const back = useRef<HTMLButtonElement>(null);

  // Focus the way back when it first appears, not each time the parent hands over an equal one.
  const opened = fromAlert !== null;
  useEffect(() => {
    if (opened) back.current?.focus();
  }, [opened]);

  useEffect(() => {
    let live = true;
    setProblem(null);
    fetchReport(api, weeks)
      .then((found) => live && setFigures(found))
      .catch((e: Error) => {
        if (!live) return;
        setFigures(null);
        setProblem(e.message);
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId, weeks]);

  const groups = groupsOf(figures);
  const colour = new Map(groups.map((g, i) => [groupKey(g), channel(i)]));
  const chosen = groups.find((g) => groupKey(g) === rule) ?? (filter.rule && groupKey(filter.rule) === rule ? filter.rule : null);
  const inFilter = (g: { label: string; typology?: string }) => !chosen || groupKey({ label: g.label, typology: g.typology ?? "" }) === rule;
  const m = figures?.monitoring;
  const raised = (m?.raised_by_rule ?? []).filter(inFilter);
  const weeksSeen = [...new Set(raised.map((w) => w.week_start))].sort();
  const team = (m?.team ?? []).filter(inFilter);
  const every = chosen ? " (every rule)" : "";

  return (
    <section aria-label={ALERT_MONITORING.title} style={{ flex: 1, overflowY: "auto", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
      {fromAlert && (
        <div role="note" aria-label="Opened from an alert" className="label"
             style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
          <span>{`From ${fromAlert.words}`}</span>
          <span aria-hidden>·</span>
          <button ref={back} type="button" className="btn" onClick={fromAlert.onBack}>← Back to your alerts</button>
        </div>
      )}
      <header style={{ display: "flex", gap: "var(--sp-12)", alignItems: "center", flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>{ALERT_MONITORING.title}</h3>
        <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          Rule
          <Select aria-label="Rule" value={rule} onChange={(e) => setRule(e.target.value)}>
            <option value={ALL}>Every rule</option>
            {(chosen && !groups.some((g) => groupKey(g) === rule) ? [chosen, ...groups] : groups).map((g) => (
              <option key={groupKey(g)} value={groupKey(g)}>{groupName(g)}</option>
            ))}
          </Select>
        </label>
        <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          Period
          <Select aria-label="Period" value={String(weeks)} onChange={(e) => setWeeks(Number(e.target.value))}>
            {PERIODS.map((p) => (
              <option key={p} value={p}>{`Last ${p} weeks`}</option>
            ))}
          </Select>
        </label>
      </header>
      <p className="label" style={{ margin: 0 }}>
        Counted for you: an alert concerning anything you cannot see is in no figure here.
      </p>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      {!figures && !problem && <p className="label">Counting…</p>}
      {figures && m && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(22rem, 1fr))", gap: "var(--sp-16)" }}>
          <AlertsPanel api={api} monitoring={m} only={chosen} onOpenAlert={onOpenAlert} outlined={fromAlert !== null} />
          <Section title="Raised each week">
            <p className="value" style={{ margin: 0 }}>
              {`${plural(raised.reduce((n, w) => n + w.count, 0), "alert")} raised in the last ${figures.period_weeks} weeks`}
            </p>
            {weeksSeen.length === 0 ? (
              <p className="label" style={{ margin: 0 }}>No alerts were raised in this period.</p>
            ) : (
              <Bars label="Raised each week" rows={weeksSeen.map((week) => ({
                label: `Week of ${week}`,
                value: raised.filter((w) => w.week_start === week).reduce((n, w) => n + w.count, 0),
                colour: chosen ? colour.get(rule) : "--brass",
              }))} />
            )}
          </Section>
          <Section title="Raised by rule">
            <Bars label="Raised by rule" rows={groups.filter(inFilter).map((g) => ({
              label: groupName(g),
              value: raised.filter((w) => groupKey({ label: w.label, typology: w.typology ?? "" }) === groupKey(g)).reduce((n, w) => n + w.count, 0),
              colour: colour.get(groupKey(g)),
            }))} />
          </Section>
          <Section title={`Closed by outcome${every}`}>
            <Bars label="Closed by outcome" rows={[...new Set((m.closed_by_outcome ?? []).map((w) => w.label))].map((label) => ({
              label: closingReasonLabel(label === "closed" ? null : label) || "Closed, no outcome",
              value: (m.closed_by_outcome ?? []).filter((w) => w.label === label).reduce((n, w) => n + w.count, 0),
            }))} />
          </Section>
          <Section title={`Time to close${every}`}>
            <Bars label="Time to close" rows={(m.time_to_close ?? []).map((c) => ({ label: c.label, value: c.value }))} />
          </Section>
          {(!chosen || chosen.label === "hotlists") && (
            <Section title="Hotlist matches">
              <p className="value" style={{ margin: 0 }}>
                {plural((m.hotlist_matches ?? []).reduce((n, w) => n + w.count, 0), "match", "matches")}
              </p>
            </Section>
          )}
          <Section title="Team view">
            <table className="table" aria-label="Team view by rule">
              <thead>
                <tr>
                  <th>Rule</th>
                  <th style={{ textAlign: "right" }}>Unassigned</th>
                  <th style={{ textAlign: "right" }}>Mine</th>
                  <th style={{ textAlign: "right" }}>Older than 7 days</th>
                  <th style={{ textAlign: "right" }}>Closed as not of interest</th>
                </tr>
              </thead>
              <tbody>
                {team.map((t) => (
                  <tr key={groupKey({ label: t.label, typology: t.typology ?? "" })}>
                    <td>{groupName({ label: t.label, typology: t.typology ?? "" })}</td>
                    <td style={{ textAlign: "right" }}>{NUMBER.format(t.unassigned ?? 0)}</td>
                    <td style={{ textAlign: "right" }}>{NUMBER.format(t.mine ?? 0)}</td>
                    <td style={{ textAlign: "right" }}>{NUMBER.format(t.older_than_week ?? 0)}</td>
                    <td style={{ textAlign: "right" }}>{share(t.not_of_interest ?? 0, t.closed ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      )}
    </section>
  );
}
