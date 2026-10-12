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

export function useDecidedScreens<T extends string = ScreenName>() {
  const [decided, setDecided] = useState<Set<T>>(new Set());
  const markDecided = useCallback((name: T) => {
    setDecided((previous) => new Set(previous).add(name));
  }, []);
  return { decided, markDecided };
}

// The guided install page (`06_DECISIONS.md` ADR-114 Amendment 3, decision 6): Mode first, then
// the chosen mode's own screens in this order. "Map" is the Set-up console's Geospatial screen. The
// Set-up console's own Preflight screen is not in the flow: the install runs the doctor on Review.
export const INSTALL_MODES = ["lite", "small", "enterprise"] as const;

export const INSTALL_SCREENS = {
  lite: [
    "Mode", "Folders", "Profile", "Components", "Map", "Models", "Governance", "Demo packs",
    "Review", "Installing",
  ],
  small: [
    "Mode", "Cloud and region", "Domain", "Components", "Models", "Governance", "Demo packs",
    "Review",
  ],
  enterprise: [
    "Mode", "Cloud and region", "Domain", "Components", "Models", "Governance", "Demo packs",
    "Review",
  ],
} as const;
export type InstallScreenName = (typeof INSTALL_SCREENS)[keyof typeof INSTALL_SCREENS][number];

/** The screens a person can go to: Installing is where Install leads, never a place to go. */
export function installNav(mode: (typeof INSTALL_MODES)[number]): InstallScreenName[] {
  return INSTALL_SCREENS[mode].filter((name) => name !== "Installing");
}
