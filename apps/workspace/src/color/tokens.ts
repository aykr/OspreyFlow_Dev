// A JS-readable mirror of the handful of `docs/design/tokens.css` values
// that must be computed *before* paint (baked into a generated node SVG,
// `nodeVisual.ts`) rather than left to the CSS cascade. `docs/design/
// tokens.css` remains the single authoritative source — `tokens.test.ts`
// parses that file directly and asserts these stay in sync, so drift
// fails a test rather than surviving as a silently-stale copy (the exact
// "invariant stated in prose that no test exercises" failure mode
// `docs/SESSION_HANDOVER.md` warns about).
export const CHANNEL_HEX: Record<string, string> = {
  ochre: "#b34917",
  rose: "#b74b5e",
  plum: "#916384",
  violet: "#8364a6",
  indigo: "#677bd6",
  azure: "#61b1e6",
  cyan: "#35b9c0",
  jade: "#72b99a",
  moss: "#90b667",
};

/** A plain string, not an indexed lookup — `noUncheckedIndexedAccess`
 * otherwise makes `CHANNEL_HEX[x] ?? CHANNEL_HEX.ochre` still `string |
 * undefined`, since dot access on a `Record<string, string>` goes through
 * the same index signature. Used as the fallback for a channel name the
 * ontology declares that this file's mirror hasn't caught up to yet. */
export const FALLBACK_CHANNEL_HEX = CHANNEL_HEX.ochre as string;

export function resolveChannelHex(channel: string): string {
  return CHANNEL_HEX[channel] ?? FALLBACK_CHANNEL_HEX;
}

export const BRASS_HEX = "#c08a34";
export const TEXT_PRIMARY_DARK_HEX = "#e8eced";
export const BORDER_STRONG_DARK_HEX = "#66696a";

/** `--surface-panel` is `--n2` — the dimming/filtered-out mix target. Dark
 * only for now: Checkpoint 2 ships the dark theme as the working default
 * (`docs/design/tokens.css`'s own framing); light-theme SVG regeneration
 * is a named follow-up alongside the light-theme contrast CI check. */
export const SURFACE_PANEL_DARK_HEX = "#161a1b";
