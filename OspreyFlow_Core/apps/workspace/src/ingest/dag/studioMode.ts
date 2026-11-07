// The Studio's two modes over one pipeline (ADR-140 decision 3; Amendment 1.3: guided is the default).
// The mode is a per-person preference. With no preference store on the server, it is kept in this
// browser, keyed by the signed-in person's user name (the owner's ruling Q1 a, 7 November 2026;
// spec 09 §1.0 says so): a second person on the same browser gets their own, and every person starts
// guided. A browser that refuses storage still works, in guided mode, and forgets the choice.

export type StudioMode = "guided" | "expert";

export const DEFAULT_STUDIO_MODE: StudioMode = "guided";

export function studioModeKey(username: string | null | undefined): string {
  return `ospreyflow.studio.mode.${username ?? "anonymous"}`;
}

export function readStudioMode(username: string | null | undefined): StudioMode {
  try {
    const stored = window.localStorage.getItem(studioModeKey(username));
    return stored === "expert" || stored === "guided" ? stored : DEFAULT_STUDIO_MODE;
  } catch {
    return DEFAULT_STUDIO_MODE;
  }
}

export function writeStudioMode(username: string | null | undefined, mode: StudioMode): void {
  try {
    window.localStorage.setItem(studioModeKey(username), mode);
  } catch {
    // Storage refused (a private window, blocked site data): the choice holds for this visit only.
  }
}
