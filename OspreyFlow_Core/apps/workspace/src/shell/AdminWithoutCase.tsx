// The Admin area opened from Start with no case (ADR-114 Amendment 5 point 9): administration is the
// deployment's, not a case's, so it needs none — on a fresh install there may be none to open.
import type { ReactNode } from "react";

import { AdminPlace } from "../admin/AdminPlace";
import { StartBar } from "./StartPage";

export interface AdminWithoutCaseProps {
  apiBaseUrl: string;
  bearerToken: string;
  rights: ReadonlySet<string>;
  onStart: () => void;
  account: ReactNode;
  marking: string | null;
}

export function AdminWithoutCase({ onStart, account, marking, ...admin }: AdminWithoutCaseProps) {
  return (
    // ADR-132: the window less whatever the brand frame shows above (`brand/BrandFrame.tsx`).
    <div style={{ display: "flex", flexDirection: "column", height: "var(--workspace-height, 100vh)" }}>
      <StartBar account={account} onStart={onStart} marking={marking} />
      <AdminPlace {...admin} />
    </div>
  );
}
