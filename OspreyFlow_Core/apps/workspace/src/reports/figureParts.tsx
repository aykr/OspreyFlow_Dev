// The pieces every figure on the case's Figures tab and the Alert monitoring board is drawn with
// (ADR-111; ADR-145 Amendment 4 decisions 8 and 9): a titled section, plain bars whose number is
// always written, and the rule groups' names. Colours are the design tokens' channels only.
import type { ReactNode } from "react";

import { typologyLabel } from "../alerts/names";

export const NUMBER = new Intl.NumberFormat("en-GB");

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${NUMBER.format(n)} ${n === 1 ? one : many}`;
}

/** The channels, in the fixed order a figure's series take them (never cycled past the end: a
 * ninth series takes the last). */
export const CHANNELS = ["--ch-azure", "--ch-ochre", "--ch-jade", "--ch-plum", "--ch-rose", "--ch-cyan", "--ch-indigo", "--ch-moss"];
export const channel = (i: number): string => CHANNELS[Math.min(i, CHANNELS.length - 1)] ?? "--brass";

/** The age bands the Conduit counts open alerts in (`reports.AGE_LABELS`), in order. */
export const AGE_BANDS = ["under a day", "1 to 7 days", "7 to 30 days", "over 30 days"] as const;

/** A rule group as the feed labels it: `typology` with its typology, `hotlists` or `monitors`. */
export interface RuleGroup {
  label: string;
  typology: string;
}

export const groupKey = (g: RuleGroup): string => `${g.label}:${g.typology}`;

const KIND_GROUP: Record<string, string> = { typology: "typology", hotlist: "hotlists", monitor: "monitors" };

/** The rule group a queued alert is counted under, as the Conduit's `_RULE_GROUP` names it: the Glass's one
 * copy, read by the Alerts panel and by Home's *Open the dashboard*, so the two cannot drift apart. */
export function alertRuleGroup(row: { kind?: string | null; alert: { typology?: string | null } }): RuleGroup {
  const kind = row.kind ?? "typology";
  return { label: KIND_GROUP[kind] ?? kind, typology: kind === "typology" ? (row.alert.typology ?? "") : "" };
}

/** A rule group in words: a typology rule by its typology, never a rule's own analyst-written name. */
export function groupName(g: RuleGroup): string {
  if (g.label === "hotlists") return "Hotlists";
  if (g.label === "monitors") return "Monitors";
  return typologyLabel(g.typology || "other");
}

export function Section({ title, children, id, outlined = false }: { title: string; children: ReactNode; id?: string; outlined?: boolean }) {
  return (
    <section
      id={id}
      aria-label={title}
      data-outlined={outlined ? "true" : undefined}
      style={{
        border: outlined ? "2px solid var(--focus)" : "1px solid var(--border-subtle)",
        padding: "var(--sp-12)",
        display: "grid",
        gap: "var(--sp-8)",
        alignContent: "start",
      }}
    >
      <h3 className="value" style={{ margin: 0 }}>{title}</h3>
      {children}
    </section>
  );
}

/** One horizontal bar per row, its length the share of the largest; the number always written. */
export function Bars({ rows, label }: { rows: { label: string; value: number; colour?: string }[]; label?: string }) {
  const most = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul aria-label={label} style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
      {rows.map((r) => (
        <li key={r.label} style={{ display: "grid", gridTemplateColumns: "12rem 1fr", gap: "var(--sp-8)", alignItems: "center" }}>
          <span className="label">{`${r.label}: ${NUMBER.format(r.value)}`}</span>
          <span aria-hidden style={{ height: 10, borderRadius: "0 4px 4px 0", width: `${(r.value / most) * 100}%`, minWidth: r.value ? 2 : 0,
                                     background: `var(${r.colour ?? "--brass"})` }} />
        </li>
      ))}
    </ul>
  );
}
