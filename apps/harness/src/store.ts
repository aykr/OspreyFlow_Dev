// The summary rail's own state — `05_DEPLOYMENT.md` §2.1: "a persistent summary rail showing
// what has been decided and what is outstanding." A screen counts as decided once its own `Save`
// has succeeded at least once in this session; nothing here duplicates schema defaults to guess
// at a decision that was never made.
import { useCallback, useState } from "react";

export const SCREEN_NAMES = ["Profile", "Components", "Models", "Governance", "Geospatial"] as const;
export type ScreenName = (typeof SCREEN_NAMES)[number];

// Screens not yet built — always outstanding here, never rendered as a tab, shown in the rail only
// so an operator sees the whole six-screen shape this surface will eventually be. Preflight is
// `Stage 2 §6` part B's own item 3, not started this round (queue brief: "finish a self-consistent
// subset" — Governance and Geospatial are the subset this round completed).
export const FUTURE_SCREEN_NAMES = ["Preflight"] as const;

export function useDecidedScreens() {
  const [decided, setDecided] = useState<Set<ScreenName>>(new Set());
  const markDecided = useCallback((name: ScreenName) => {
    setDecided((previous) => new Set(previous).add(name));
  }, []);
  return { decided, markDecided };
}
