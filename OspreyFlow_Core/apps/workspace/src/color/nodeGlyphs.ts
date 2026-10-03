// The drawings an entity type's icon can be (ADR-079): twenty simple pictures on a 24-unit grid,
// drawn for this project from plain shapes, so there is nothing to download or to licence. The
// ontology names one (`EntityTypeDef.icon`); its JSON Schema holds the closed list of names and
// `nodeGlyphs.test.ts` pins that list to this one. A picture is drawn in one colour, put in where
// each drawing says `currentColor`, so it can follow the node's fill and the theme.

const GLYPHS: Readonly<Record<string, string>> = {
  person:
    '<circle cx="12" cy="8" r="4" fill="currentColor"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7z" fill="currentColor"/>',
  people:
    '<circle cx="9" cy="8" r="3.4" fill="currentColor"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6z" fill="currentColor"/><circle cx="17" cy="9" r="2.8" fill="currentColor"/><path d="M16.2 14.2c.3-.1.5-.2.8-.2 3 0 4.8 2 4.8 5.4V20h-4.3c0-2.3-.4-4.2-1.3-5.8z" fill="currentColor"/>',
  building:
    '<path fill-rule="evenodd" fill="currentColor" d="M5 21V3h10v6h4v12zM8 6h1.5v1.5H8zM11 6h1.5v1.5H11zM8 10h1.5v1.5H8zM11 10h1.5v1.5H11zM8 14h1.5v1.5H8zM11 14h1.5v1.5H11zM16 12h1.5v1.5H16zM16 16h1.5v1.5H16z"/>',
  bank: '<path fill="currentColor" d="M12 2.5 3 8v2h18V8zM5 11h2.5v7H5zM10.75 11h2.5v7h-2.5zM16.5 11H19v7h-2.5zM3 19.5h18V22H3z"/>',
  phone:
    '<path fill-rule="evenodd" fill="currentColor" d="M7 2h10a1.5 1.5 0 0 1 1.5 1.5v17A1.5 1.5 0 0 1 17 22H7a1.5 1.5 0 0 1-1.5-1.5v-17A1.5 1.5 0 0 1 7 2zM8 5v12h8V5z"/><circle cx="12" cy="19.5" r="1" fill="currentColor"/>',
  mail: '<path fill-rule="evenodd" fill="currentColor" d="M3 5h18v14H3zM4.9 6.8 12 12l7.1-5.2v1.8L12 14 4.9 8.6z"/>',
  device:
    '<path fill-rule="evenodd" fill="currentColor" d="M3 4h18v12H3zM5 6v8h14V6z"/><path fill="currentColor" d="M2 18h20v2H2z"/>',
  pin: '<path fill-rule="evenodd" fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 4.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z"/>',
  calendar:
    '<path fill-rule="evenodd" fill="currentColor" d="M3 5h18v16H3zM5 10v9h14v-9z"/><path fill="currentColor" d="M7 2h2v5H7zM15 2h2v5h-2z"/>',
  document:
    '<path fill-rule="evenodd" fill="currentColor" d="M5 2h9l5 5v15H5zM8 12h8v1.6H8zM8 15.5h8v1.6H8zM8 8.5h4v1.6H8z"/>',
  vehicle:
    '<path fill-rule="evenodd" fill="currentColor" d="M3 11l2-5h14l2 5v6H3zM7.2 8 6.2 10.5h11.6L16.8 8z"/><circle cx="7.5" cy="17.5" r="2.5" fill="currentColor"/><circle cx="16.5" cy="17.5" r="2.5" fill="currentColor"/>',
  box: '<path fill-rule="evenodd" fill="currentColor" d="M3 6h18v4H3zM4.5 11h15v9h-15zM9.5 13v2h5v-2z"/>',
  key: '<circle cx="7.5" cy="9" r="4.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path fill="currentColor" d="M10.5 12 20 21.5l-1.6 1.6L9 13.6z"/><path fill="currentColor" d="M16 17.5l2.2-2.2 1.6 1.6-2.2 2.2z"/>',
  globe:
    '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><ellipse cx="12" cy="12" rx="4" ry="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3 12h18" fill="none" stroke="currentColor" stroke-width="2"/>',
  card: '<rect x="2.5" y="5" width="19" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path fill="currentColor" d="M2.5 9.5h19v2.5h-19z"/><rect x="5" y="14.5" width="5" height="2" fill="currentColor"/>',
  shield: '<path fill="currentColor" d="M12 2.5 4.5 5.5v6c0 4.5 3.2 8.2 7.5 10 4.3-1.8 7.5-5.5 7.5-10v-6z"/>',
  flag: '<path fill="currentColor" d="M5 2h2v20H5z"/><path fill="currentColor" d="M7 3.5h12l-3 4.5 3 4.5H7z"/>',
  link: '<rect x="2.5" y="8.5" width="11" height="7" rx="3.5" fill="none" stroke="currentColor" stroke-width="2.2"/><rect x="10.5" y="8.5" width="11" height="7" rx="3.5" fill="none" stroke="currentColor" stroke-width="2.2"/>',
  tag: '<path fill-rule="evenodd" fill="currentColor" d="M3 3h8.5l9.5 9.5-8.5 8.5L3 11.5zM7.5 6.2a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z"/>',
  camera:
    '<path fill-rule="evenodd" fill="currentColor" d="M3 7h4l1.5-2.5h7L17 7h4v13H3zM12 9.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/>',
};

/** The names an ontology may give an entity type's `icon`. */
export const GLYPH_NAMES: readonly string[] = Object.keys(GLYPHS);

export function hasGlyph(name: string | null | undefined): boolean {
  return typeof name === "string" && Object.prototype.hasOwnProperty.call(GLYPHS, name);
}

/** The drawing for `name`, in `colourHex`, as SVG elements on a 24-unit grid; `null` for a name
 * that is not on the list. */
export function glyphMarkup(name: string | null | undefined, colourHex: string): string | null {
  if (!hasGlyph(name)) return null;
  return GLYPHS[name as string]!.replaceAll("currentColor", colourHex);
}
