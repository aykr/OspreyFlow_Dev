// A queued alert's rule group (ADR-111; ADR-145 Amendment 4 decisions 8 and 9): the Figures' one copy of how an alert
// is counted, read by the Alerts panel and by Home's *Open the dashboard*, so the two cannot drift apart. Moved out of
// `reports/figureParts.tsx` (a React file) so the plain Home figures can read it (ADR-152 R2, PL4 slice D3e).

/** A rule group as the feed labels it: `typology` with its typology, `hotlists` or `monitors`. */
export interface RuleGroup {
  label: string;
  typology: string;
}

const KIND_GROUP: Record<string, string> = { typology: "typology", hotlist: "hotlists", monitor: "monitors", analyst: "analyst", drawn_watch: "drawn_items" };

/** The rule group a queued alert is counted under, as the Conduit's `_RULE_GROUP` names it: the Glass's one
 * copy, read by the Alerts panel and by Home's *Open the dashboard*, so the two cannot drift apart. */
export function alertRuleGroup(row: { kind?: string | null; alert: { typology?: string | null } }): RuleGroup {
  const kind = row.kind ?? "typology";
  return { label: KIND_GROUP[kind] ?? kind, typology: kind === "typology" ? (row.alert.typology ?? "") : "" };
}
