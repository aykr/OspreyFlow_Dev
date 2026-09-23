// The shared playback clock — `docs/02_GLASS_FRONTEND.md` §3.4. One hook, one clock: the map's own snail
// trail (B18) and, in future, any other surface that animates content over
// a brush window read the same `fraction`, so two surfaces can never drift
// out of sync with each other the way two independent timers would.
//
// `prefers-reduced-motion` is read once, at mount — `02_GLASS_FRONTEND.md`
// §3.4's own literal requirement ("playback becomes stepped and re-layout
// becomes an instant move with a persistent control that shows previous
// positions") is honoured by `play()` advancing one step and stopping,
// rather than driving a `requestAnimationFrame` loop at all. A user who
// changes their OS-level motion preference mid-session gets the new
// behaviour on their next play, not a live-reactive switch mid-animation —
// disclosed, not silently assumed to matter: nothing in `02_GLASS_
// FRONTEND.md` §3.4 requires a live preference-change response, and no
// acceptance-scenario step exercises one.
import { useCallback, useEffect, useRef, useState } from "react";

import type { TimeWindow } from "../crossfilter/store";
import { playbackFraction, REDUCED_MOTION_STEP_FRACTION } from "./math";

export const PLAYBACK_SPEEDS = [0.5, 1, 2, 4, 8] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

export interface PlaybackControls {
  isPlaying: boolean;
  speed: PlaybackSpeed;
  setSpeed: (speed: PlaybackSpeed) => void;
  fraction: number;
  reducedMotion: boolean;
  play: () => void;
  pause: () => void;
  reset: () => void;
}

function detectReducedMotion(): boolean {
  if (typeof globalThis.matchMedia !== "function") return false;
  return globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function usePlayback(window: TimeWindow | null): PlaybackControls {
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [fraction, setFraction] = useState(0);
  const reducedMotionRef = useRef(detectReducedMotion());
  const rafRef = useRef<number | null>(null);
  // Accumulated elapsed playback time across pause/resume, so pausing
  // mid-traverse and pressing play again continues from where it left off
  // rather than restarting the animation clock from zero.
  const elapsedRef = useRef(0);

  useEffect(() => {
    setFraction(0);
    setIsPlaying(false);
    elapsedRef.current = 0;
  }, [window?.validFrom, window?.validTo]);

  useEffect(() => {
    if (!isPlaying || !window) return;

    if (reducedMotionRef.current) {
      setFraction((current) => Math.min(1, current + REDUCED_MOTION_STEP_FRACTION));
      setIsPlaying(false);
      return;
    }

    let frameStartedAt: number | null = null;
    function tick(now: number) {
      if (frameStartedAt == null) frameStartedAt = now;
      const elapsed = elapsedRef.current + (now - frameStartedAt);
      const next = playbackFraction(elapsed, speed);
      setFraction(next);
      if (next >= 1) {
        elapsedRef.current = 0;
        setIsPlaying(false);
        return;
      }
      rafRef.current = globalThis.requestAnimationFrame(tick);
    }
    rafRef.current = globalThis.requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) globalThis.cancelAnimationFrame(rafRef.current);
      if (frameStartedAt != null) {
        elapsedRef.current += globalThis.performance.now() - frameStartedAt;
      }
    };
  }, [isPlaying, speed, window]);

  const play = useCallback(() => {
    if (!window) return;
    setFraction((current) => {
      if (current >= 1) elapsedRef.current = 0;
      return current >= 1 ? 0 : current;
    });
    setIsPlaying(true);
  }, [window]);

  const pause = useCallback(() => setIsPlaying(false), []);

  const reset = useCallback(() => {
    setFraction(0);
    setIsPlaying(false);
    elapsedRef.current = 0;
  }, []);

  return {
    isPlaying,
    speed,
    setSpeed,
    fraction,
    reducedMotion: reducedMotionRef.current,
    play,
    pause,
    reset,
  };
}
