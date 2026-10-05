// What a person reads for a link (ADR-091). The type's `name` (COMMUNICATED_WITH) is the key stored
// on every link and is shown only where an identifier is wanted (the Inspector's Type ID row);
// everywhere else a link reads by its type's label, in sentence case, and its count is named by what
// it counts: "Communicated with · 3 emails".

/** The part of a type definition this needs; `EdgeTypeDef` and `EdgeTypeStyle` both fit it. */
export interface NamedType {
  name: string;
  label?: string | null;
}

/** The type's display name: its declared label, or its name in sentence case. */
export function linkTypeName(type: string, types: readonly NamedType[]): string {
  const declared = types.find((t) => t.name === type)?.label?.trim();
  if (declared) return declared;
  const words = type.toLowerCase().split("_").filter(Boolean);
  if (words.length === 0) return type;
  const sentence = words.join(" ");
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

const COUNT = new Intl.NumberFormat("en-GB");

/** "Communicated with · 3 emails", "Owns · 1 record". */
export function linkCaption(
  typeName: string,
  count: number,
  noun: "emails" | "messages" | "events",
): string {
  const unit = noun === "emails" ? "email" : noun === "messages" ? "message" : "record";
  return `${typeName} · ${COUNT.format(count)} ${count === 1 ? unit : `${unit}s`}`;
}
