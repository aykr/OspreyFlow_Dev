// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Name = string;
export type From = string[];
export type To = string[];
export type Directed = boolean;
export type Temporal = boolean;
export type System = boolean;
export type Name1 = string;
export type PropertyType = "string" | "string[]" | "date" | "datetime" | "integer" | "float" | "boolean" | "enum";
export type Indexed = boolean;
export type Required = boolean;
export type Sensitivity = ("low" | "medium" | "high") | null;
export type Values = string[] | null;
export type Properties = PropertyDef[];

export interface EdgeTypeDef {
  name: Name;
  from: From;
  to: To;
  directed?: Directed;
  temporal?: Temporal;
  system?: System;
  properties?: Properties;
  [k: string]: unknown;
}
export interface PropertyDef {
  name: Name1;
  type: PropertyType;
  indexed?: Indexed;
  required?: Required;
  sensitivity?: Sensitivity;
  values?: Values;
  [k: string]: unknown;
}
