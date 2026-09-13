// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py and _pending_port_placeholders.py, via generate_ts.py
export type Name = string;
export type PropertyType = "string" | "string[]" | "date" | "datetime" | "integer" | "float" | "boolean" | "enum";
export type Indexed = boolean;
export type Required = boolean;
export type Sensitivity = ("low" | "medium" | "high") | null;
export type Values = string[] | null;

export interface PropertyDef {
  name: Name;
  type: PropertyType;
  indexed?: Indexed;
  required?: Required;
  sensitivity?: Sensitivity;
  values?: Values;
  [k: string]: unknown;
}
