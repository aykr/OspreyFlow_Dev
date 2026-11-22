// Icons chosen by a property's value (ADR-128 Decision 4, B7). The ontology lets an entity type name
// one enum property and map some of its values to drawings (`EntityTypeDef.icon_by_value`); a node
// whose value is mapped is drawn with that drawing in place of its type's, and any other node,
// including one with no such property, keeps the type's. Shape and colour are never touched: they
// are the type's. This module only answers "which drawing, if any", and words what it means for the
// legend and the Inspector; the order against the entity's picture and the analyst's choice is
// `iconChoices.ts`'s.
import { glyphMarkup, hasGlyph } from "../color/nodeGlyphs";

/** The rule an entity type declares: the enum property it reads, and some of its values' drawings. */
export interface IconByValueRule {
  property: string;
  icons: Readonly<Record<string, string>>;
}

export interface ValueIcon {
  /** The drawing's name, on the closed list of `nodeGlyphs.ts`. */
  glyph: string;
  /** The value the node holds, which is what the drawing stands for. */
  value: string;
}

/** The drawing a node's `properties` give under `rule`, or `null` when it gives none: no rule, no
 * such property, a value that is not text, a value the map leaves out, or a name the Glass cannot
 * draw. A value is looked up as its own key only, so one spelled like an `Object` property
 * (`constructor`) is not a hit. */
export function valueIconFor(
  rule: IconByValueRule | null | undefined,
  properties: Readonly<Record<string, unknown>> | undefined,
): ValueIcon | null {
  if (!rule || !properties) return null;
  const value = properties[rule.property];
  if (typeof value !== "string") return null;
  if (!Object.prototype.hasOwnProperty.call(rule.icons, value)) return null;
  const glyph = rule.icons[value];
  if (typeof glyph !== "string" || !hasGlyph(glyph)) return null;
  return { glyph, value };
}

function words(name: string): string {
  return name.replaceAll("_", " ").replaceAll("-", " ");
}

/** What a value icon means, in words: "Keypad: Endpoint, endpoint kind handle". */
export function describeValueIcon(type: string, property: string, value: string, glyph: string): string {
  const label = words(glyph);
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}: ${type}, ${words(property)} ${words(value)}`;
}

/** The Inspector's sentence for a node's value icon: "Keypad (endpoint kind handle)". */
export function describeIconForValue(property: string, given: ValueIcon): string {
  const label = words(given.glyph);
  return `${label.charAt(0).toUpperCase()}${label.slice(1)} (${words(property)} ${words(given.value)})`;
}

/** The drawing as a small picture to put in the page, in `colourHex`; `null` for a name not on the list. */
export function glyphImageUri(glyph: string, colourHex: string): string | null {
  const markup = glyphMarkup(glyph, colourHex);
  if (markup === null) return null;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">${markup}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
