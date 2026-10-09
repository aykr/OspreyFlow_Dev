// The colours the Map stage's canvas paints with, from the themed palette (ADR-070). It once used
// the dark theme's constants in either theme, so in the light theme the entity picked as a link's
// start was painted #e8eced on #f7fbfc and vanished (9 October 2026).
import type { Palette } from "../../color/palette";

export interface MapNodeState {
  selected: boolean;
  linkFrom: boolean;
  visual?: { channel: string };
}

/** Selected is brass; the link's chosen start is drawn as a path end (primary text); otherwise the
 * type's channel, or neutral for a type the ontology does not know (DESIGN.md §3.7). */
export function mapNodeColour(state: MapNodeState, palette: Palette): string {
  if (state.selected) return palette.brass;
  if (state.linkFrom) return palette.textPrimary;
  return state.visual ? palette.channel(state.visual.channel) : palette.borderStrong;
}

export function mapCanvasColours(palette: Palette): { label: string; edge: string } {
  return { label: palette.textPrimary, edge: palette.textSecondary };
}
