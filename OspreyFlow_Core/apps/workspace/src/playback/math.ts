// Pure math for the shared playback clock — `spec/02_GLASS_FRONTEND.md` §3.4
// ("Playback — animate the brush forward at 0.5x to 8x"), extracted out of
// `usePlayback.ts` the same "pure-function-first" way `timeline/math.ts`
// already extracts `windowFromZoomPercent` out of `Timeline.tsx`: testable
// without a `requestAnimationFrame` loop or a DOM.
import type { TimeWindow } from "../crossfilter/store";

/** A full traverse of the brush window at 1x takes this long, in real
 * milliseconds. Not named anywhere in `02_GLASS_FRONTEND.md` §3.4, which
 * states the *speed* range (0.5x-8x) but not a base duration for "1x" to
 * multiply — a real spec gap, recorded here rather than silently assumed:
 * 8 seconds is this stage's own chosen value, long enough to read a dense
 * timeline's own movement, short enough not to feel stalled at 0.5x (4s
 * minimum, 16s maximum across the documented speed range). */
export const PLAYBACK_DURATION_MS_AT_1X = 8000;

/** `02_GLASS_FRONTEND.md` §3.4: "The design system fixes the interpolation
 * at 420ms with a dedicated easing curve." Applied by a consuming
 * component's own CSS transition on whatever value it animates (a map
 * marker's lat/lng, say) — this constant is the one place that duration is
 * named, so every consumer reads the same number rather than each picking
 * its own. */
export const INTERPOLATION_MS = 420;

/** Fraction (0-1, clamped) of the window traversed after `elapsedMs` of
 * real playback time at `speed`. Higher speed multiplies how much fraction
 * each real millisecond covers; it never changes what "the whole window"
 * means. */
export function playbackFraction(elapsedMs: number, speed: number): number {
  if (PLAYBACK_DURATION_MS_AT_1X <= 0) return 1;
  const fraction = (elapsedMs * speed) / PLAYBACK_DURATION_MS_AT_1X;
  return Math.max(0, Math.min(1, fraction));
}

/** The wall-clock instant `fraction` of the way through `window` — the
 * playback "now" a consuming surface reveals content up to. `validTo` may
 * be absent (an open-ended window, `crossfilter/store.ts`'s own
 * `TimeWindow` shape); an open window has nothing to animate across, so it
 * collapses to `validFrom` itself rather than an undefined end point. */
export function instantAtFraction(window: TimeWindow, fraction: number): Date {
  const from = new Date(window.validFrom).getTime();
  const to = window.validTo ? new Date(window.validTo).getTime() : from;
  const clamped = Math.max(0, Math.min(1, fraction));
  return new Date(from + (to - from) * clamped);
}

/** Every item at or before `instant`, in the order given — the snail
 * trail's own "ordered track... animates under playback"
 * (`08_ACCEPTANCE_SCENARIOS.md` B18) is a real content change over time,
 * not a rendering trick layered on a static list. Sightings arrive already
 * ordered by `occurred_at` (`AnalyticsPort.list_sightings`'s own
 * docstring), so this is a single forward pass, not a sort — and it stops
 * at the first item past the cutoff rather than scanning the whole list on
 * every animation frame. */
export function itemsUpTo<T extends { occurred_at: string }>(
  items: readonly T[],
  instant: Date,
): T[] {
  const cutoff = instant.getTime();
  const result: T[] = [];
  for (const item of items) {
    if (new Date(item.occurred_at).getTime() > cutoff) break;
    result.push(item);
  }
  return result;
}

/** `prefers-reduced-motion` playback advances in discrete steps, never a
 * continuous animation (`02_GLASS_FRONTEND.md` §3.4: "playback becomes
 * stepped... a persistent control that shows previous positions"). One
 * press of the step control = this much of the window revealed at once. */
export const REDUCED_MOTION_STEP_FRACTION = 0.1;
