// What the Admin place knows of its inviter, provided to the People screen (AD2). The place reads `GET /v1/me` and provides
// it; the screen only consumes it, so the screen's walk (`test_admin_sections.py`) reaches no route of its own beyond the
// section's. The types and the functions that work out what an inviter may give are plain, and are in
// `packages/glass-shared` (`admin/inviter.ts`, ADR-152 decision 6); the context and the hook stay here with React.
import { createContext, useContext } from "react";

import type { InviterRead } from "@ospreyflow/glass-shared";

/** Waiting by default: a screen outside the Admin place, which reads nothing, offers no invitation. */
export const InviterContext = createContext<InviterRead>({ state: "waiting" });

export function useInviter(): InviterRead {
  return useContext(InviterContext);
}
