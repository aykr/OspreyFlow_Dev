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

export const TYPOLOGY_LABELS: Record<string, string> = {
  structuring: "Structuring",
  rapid_movement: "Rapid movement",
  circular_flow: "Circular flow",
  kyc_screening: "KYC screening",
  shared_attributes: "Shared contact details",
  document_verification: "Unverified customer",
};

export function typologyLabel(typology: string | null | undefined): string {
  return (typology && TYPOLOGY_LABELS[typology]) || "Alert";
}

const MONEY = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });

export function money(amount: number | null | undefined): string {
  return amount == null ? "—" : MONEY.format(amount);
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}
