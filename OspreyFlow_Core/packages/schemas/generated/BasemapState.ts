// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ProviderId = string;
export type File = string;
export type Built = boolean;
export type SizeBytes = number | null;
export type BuiltAt = string | null;
export type Basemaps = LocalBasemap[];
export type GlyphsInstalled = boolean;
export type GlyphFonts = string[];
export type BuilderReady = boolean;
export type BuilderState = string;
export type Regions = string[];

export interface BasemapState {
  basemaps: Basemaps;
  glyphs_installed: GlyphsInstalled;
  glyph_fonts: GlyphFonts;
  builder_ready: BuilderReady;
  builder_state: BuilderState;
  regions: Regions;
  [k: string]: unknown;
}
/**
 * A tier-1 provider's local file, as the Conduit sees it.
 */
export interface LocalBasemap {
  provider_id: ProviderId;
  file: File;
  built: Built;
  size_bytes?: SizeBytes;
  built_at?: BuiltAt;
  [k: string]: unknown;
}
