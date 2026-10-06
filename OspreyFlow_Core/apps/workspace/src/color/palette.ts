// The colours a canvas needs, by theme (ADR-070). A canvas paints with hex values, not CSS
// variables, so the two themes' values are mirrored here; `tokens.test.ts` parses tokens.css and
// fails if either drifts from it. Dark is the constants already in `tokens.ts`.
import {
  BORDER_STRONG_DARK_HEX,
  BORDER_SUBTLE_DARK_HEX,
  BRASS_HEX,
  resolveChannelHex,
  SEQ_HEX,
  SURFACE_APP_DARK_HEX,
  SURFACE_PANEL_DARK_HEX,
  SURFACE_HOVER_DARK_HEX,
  SURFACE_RAISED_DARK_HEX,
  SURFACE_SUNKEN_DARK_HEX,
  TEXT_PRIMARY_DARK_HEX,
  TEXT_SECONDARY_DARK_HEX,
} from "./tokens";
import { currentTheme, type Theme } from "../theme/theme";

export interface Palette {
  channel: (name: string) => string;
  textPrimary: string;
  textSecondary: string;
  borderStrong: string;
  borderSubtle: string;
  surfaceSunken: string;
  surfaceApp: string;
  surfacePanel: string;
  surfaceRaised: string;
  surfaceHover: string;
  brass: string;
  seq: readonly [string, string, string, string, string, string];
}

const LIGHT_CHANNEL_HEX: Record<string, string> = {
  ochre: "#83330d",
  rose: "#7e032c",
  plum: "#632a55",
  violet: "#562182",
  indigo: "#5367cb",
  azure: "#3682b2",
  cyan: "#2b9095",
  jade: "#2f8364",
  moss: "#6c8c4a",
};

const DARK: Palette = {
  channel: resolveChannelHex,
  textPrimary: TEXT_PRIMARY_DARK_HEX,
  textSecondary: TEXT_SECONDARY_DARK_HEX,
  borderStrong: BORDER_STRONG_DARK_HEX,
  borderSubtle: BORDER_SUBTLE_DARK_HEX,
  surfaceSunken: SURFACE_SUNKEN_DARK_HEX,
  surfaceApp: SURFACE_APP_DARK_HEX,
  surfacePanel: SURFACE_PANEL_DARK_HEX,
  surfaceRaised: SURFACE_RAISED_DARK_HEX,
  surfaceHover: SURFACE_HOVER_DARK_HEX,
  brass: BRASS_HEX,
  seq: SEQ_HEX,
};

const LIGHT: Palette = {
  channel: (name) => LIGHT_CHANNEL_HEX[name] ?? (LIGHT_CHANNEL_HEX.ochre as string),
  textPrimary: "#191b1c",
  textSecondary: "#4b4e4e",
  borderStrong: "#a2a5a6",
  borderSubtle: "#ced2d2",
  surfaceSunken: "#ffffff",
  surfaceApp: "#f7fbfc",
  surfacePanel: "#f1f4f5",
  surfaceRaised: "#e8eced",
  surfaceHover: "#dde0e1",
  brass: "#8a6318",
  seq: ["#cfebec", "#a0ced0", "#6eaeb2", "#358f94", "#007177", "#00535b"],
};

export function paletteFor(theme: Theme): Palette {
  return theme === "light" ? LIGHT : DARK;
}

/** The palette for the theme the page is showing now. */
export function activePalette(): Palette {
  return paletteFor(currentTheme());
}
