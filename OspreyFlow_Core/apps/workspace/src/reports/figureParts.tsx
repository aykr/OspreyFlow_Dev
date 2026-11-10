// The pieces every figure on the case's Figures tab and the Alert monitoring board is drawn with
// (ADR-111; ADR-145 Amendment 4 decisions 8 and 9): a titled section, plain bars whose number is
// always written, and the rule groups' names. Colours are the design tokens' channels only.
import type { ReactNode } from "react";

import type { MonitoringFigures } from "../../../../packages/schemas/generated";
import { typologyLabel } from "../alerts/names";

export const NUMBER = new Intl.NumberFormat("en-GB");

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${NUMBER.format(n)} ${n === 1 ? one : many}`;
}

/** The channels, in the fixed order a figure's series take them (never cycled past the end: a
 * ninth series takes the last). */
export const CHANNELS = ["--ch-azure", "--ch-ochre", "--ch-jade", "--ch-plum", "--ch-rose", "--ch-cyan", "--ch-indigo", "--ch-moss"];
export const channel = (i: number): string => CHANNELS[Math.min(i, CHANNELS.length - 1)] ?? "--brass";

/** The generated age band (`schemas.domain.AgeBand`), read from the feed's own type. */
export type AgeBand = NonNullable<MonitoringFigures["open_by_source"]>[number]["age"];

/** The age bands the Conduit counts open alerts in (`reports.AGE_LABELS`), in order. Typed against
 * the generated `AgeBand` both ways: a band the schema drops is a type error here, and so is one it
 * adds that this list leaves out (`_EVERY_BAND`). */
export const AGE_BANDS = ["under a day", "1 to 7 days", "7 to 30 days", "over 30 days"] as const satisfies readonly AgeBand[];
const _EVERY_BAND: Exclude<AgeBand, (typeof AGE_BANDS)[number]> extends never ? true : never = true;
void _EVERY_BAND;

/** A rule group as the feed labels it: `typology` with its typology, `hotlists` or `monitors`. */
export interface RuleGroup {
  label: string;
  typology: string;
}

export const groupKey = (g: RuleGroup): string => `${g.label}:${g.typology}`;

const KIND_GROUP: Record<string, string> = { typology: "typology", hotlist: "hotlists", monitor: "monitors", analyst: "analyst", drawn_watch: "drawn_items" };
/** The non-typology groups' names; a kind added later (one the Conduit counts under its own name) is
 * said by that name, never folded into a typology or another kind. */
const GROUP_NAMES: Record<string, string> = { hotlists: "Hotlists", monitors: "Monitors", analyst: "Raised by an analyst", drawn_items: "Drawn items" };

/** The rule group a queued alert is counted under, as the Conduit's `_RULE_GROUP` names it: the Glass's one
 * copy, read by the Alerts panel and by Home's *Open the dashboard*, so the two cannot drift apart. */
export function alertRuleGroup(row: { kind?: string | null; alert: { typology?: string | null } }): RuleGroup {
  const kind = row.kind ?? "typology";
  return { label: KIND_GROUP[kind] ?? kind, typology: kind === "typology" ? (row.alert.typology ?? "") : "" };
}

/** A rule group in words: a typology rule by its typology, never a rule's own analyst-written name. */
export function groupName(g: RuleGroup): string {
  if (g.label === "typology") return typologyLabel(g.typology || "other");
  const named = GROUP_NAMES[g.label];
  if (named) return named;
  const words = g.label.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
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
