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

/** `null` while unread or when `GET /v1/me` does not answer: the form then offers the whole vocabulary and the Conduit
 * refuses what it must. */
export const InviterContext = createContext<Inviter | null>(null);

export function useInviter(): Inviter | null {
  return useContext(InviterContext);
}

/** The classifications an inviter may give, lowest first as the scheme orders them: their own and those below it, as the
 * Conduit's `_within_your_reach` allows. A clearance outside the scheme can give none. Unread, every one is offered. */
export function givableLevels(levels: string[], inviter: Inviter | null): string[] {
  if (!inviter) return levels;
  const own = levels.indexOf(inviter.clearance);
  return own < 0 ? [] : levels.slice(0, own + 1);
}

/** The handling codes an inviter may give: those they can receive themselves. Unread, every one is offered. */
export function givableCodes(codes: string[], inviter: Inviter | null): string[] {
  return inviter ? codes.filter((c) => inviter.codes.includes(c)) : codes;
}
