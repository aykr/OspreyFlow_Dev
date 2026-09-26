// The summary rail's own state — `05_DEPLOYMENT.md` §2.1: "a persistent summary rail showing
// what has been decided and what is outstanding." A screen counts as decided once its own `Save`
// has succeeded at least once in this session; nothing here duplicates schema defaults to guess
// at a decision that was never made.
import { useCallback, useState } from "react";

export const SCREEN_NAMES = [
  "Profile",
  "Components",
  "Models",
  "Governance",
  "Geospatial",
  "Preflight",
] as const;
export type ScreenName = (typeof SCREEN_NAMES)[number];

// All six screens `05_DEPLOYMENT.md` §2.1 names are now built — nothing left to list here as
// outstanding. Launch itself (round 03d) lives inside the Preflight screen rather than as a
// seventh tab, the same way the artefacts diff does.
export const FUTURE_SCREEN_NAMES: readonly ScreenName[] = [];

export function useDecidedScreens() {
  const [decided, setDecided] = useState<Set<ScreenName>>(new Set());
  const markDecided = useCallback((name: ScreenName) => {
    setDecided((previous) => new Set(previous).add(name));
  }, []);
  return { decided, markDecided };
}
