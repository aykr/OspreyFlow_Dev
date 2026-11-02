// How the Alerts place names what an alert concerns — the same order of telling properties the
// server's summary uses (`services/api/alert_queue.py::node_name`), so the two never disagree.
import type { Node } from "../../../../packages/schemas/generated";

const NAME_PROPERTIES = ["name", "account_number", "value_normalised", "family_name", "title", "rule_id"];

export function nodeName(node: Node): string {
  const props = node.properties as Record<string, unknown>;
  for (const key of NAME_PROPERTIES) {
    const value = props[key];
    if (typeof value === "string" && value.trim()) {
      if (key === "family_name" && typeof props.given_names === "string") return `${props.given_names} ${value}`;
      return value;
    }
  }
  return `${node.type} ${node.id.slice(-6)}`;
}

/** One line of "What this alert concerns": the node's name and type and, for a screening list's own
 * entry (`kyc_rules._listed_write` gives it `listing` and `list_name`), whose entry it is. A screening
 * alert cites the customer and that entry, joined by an inferred same-as link; the two are never
 * merged (rule 6), and named alike they read as one person listed twice (step 9d finding 2). */
export function concernWords(node: Node): string {
  const props = node.properties as Record<string, unknown>;
  const list = props.list_name;
  const listed = typeof props.listing === "string" && typeof list === "string" && list.trim() !== "";
  return `${nodeName(node)} · ${node.type}${listed ? ` · the entry on ${list}` : ""}`;
}

export const TYPOLOGY_LABELS: Record<string, string> = {
  structuring: "Structuring",
  rapid_movement: "Rapid movement",
  circular_flow: "Circular flow",
  kyc_screening: "KYC screening",
  shared_attributes: "Shared contact details",
  document_verification: "Unverified customer",
  pattern: "Drawn pattern",
  sentence: "Sentence rule",
  // ADR-133 stage (c): the new AML templates.
  high_risk_jurisdiction: "High-risk jurisdiction",
  large_cash: "Large cash",
  dormant_reactivated: "Dormant account reactivated",
  velocity_rise: "Sudden rise in velocity",
};

export function typologyLabel(typology: string | null | undefined): string {
  return (typology && TYPOLOGY_LABELS[typology]) || "Alert";
}

/** A rule is named by what it checks; its alert, above, by what it found. */
const RULE_LABELS: Record<string, string> = {
  document_verification: "Document verification",
};

export function ruleTypologyLabel(typology: string | null | undefined): string {
  return (typology && RULE_LABELS[typology]) || typologyLabel(typology);
}

const MONEY = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });

export function money(amount: number | null | undefined): string {
  return amount == null ? "—" : MONEY.format(amount);
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}
