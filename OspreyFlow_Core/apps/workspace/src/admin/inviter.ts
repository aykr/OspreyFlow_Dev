// What the person inviting holds, for what an invitation may offer (AD2): their clearance and the handling codes they can
// receive. The Admin place reads it (`GET /v1/me`) and provides it; the People screen only consumes it, so the screen's
// walk (`test_admin_sections.py`) reaches no route of its own beyond the section's. Imports nothing but React, for that
// reason. The Glass's filter is a convenience, never the control: the Conduit refuses what is beyond the inviter
// (`_within_your_reach`, 403).
import { createContext, useContext } from "react";

export interface Inviter {
  clearance: string;
  codes: string[];
}

/** What the Admin place knows of its inviter. The invite form is drawn only once the details have arrived (`ready`), so no
 * choice is ever made before them and none is filtered, reset or hidden afterwards; `waiting` and `unavailable` each say
 * so in words instead. */
export type InviterRead = { state: "waiting" } | { state: "unavailable" } | { state: "ready"; inviter: Inviter };

/** Waiting by default: a screen outside the Admin place, which reads nothing, offers no invitation. */
export const InviterContext = createContext<InviterRead>({ state: "waiting" });

export function useInviter(): InviterRead {
  return useContext(InviterContext);
}

/** The classifications an inviter may give, lowest first as the scheme orders them: their own and those below it, as the
 * Conduit's `_within_your_reach` allows. A clearance outside the scheme can give none. */
export function givableLevels(levels: string[], inviter: Inviter): string[] {
  const own = levels.indexOf(inviter.clearance);
  return own < 0 ? [] : levels.slice(0, own + 1);
}

/** The handling codes an inviter may give: those they can receive themselves. */
export function givableCodes(codes: string[], inviter: Inviter): string[] {
  return codes.filter((c) => inviter.codes.includes(c));
}
