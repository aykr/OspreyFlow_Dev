// What the map draws over the basemap, and in which of the theme's colours (ADR-070): the graph's
// markers, links and labels, and a sighting trail. One place, read by `MapView.tsx` and by the
// three themes' contrast check (`map-verify/contrast.spec.ts`), so the check measures the colours
// the map really uses rather than a copy of them.
import type { Palette } from "../color/palette";

export interface OverlayColours {
  /** A plotted node: brass, the accent (sigma's own grey was unreadable on the light basemap). */
  marker: string;
  link: string;
  label: string;
  /** A sighting trail is data, so the sequential ramp, never brass (ADR-097). */
  trail: string;
  trailPoint: string;
}

export function overlayColours(palette: Palette): OverlayColours {
  return {
    marker: palette.brass,
    link: palette.textSecondary,
    label: palette.textPrimary,
    trail: palette.seq[4],
    trailPoint: palette.seq[5],
  };
}
