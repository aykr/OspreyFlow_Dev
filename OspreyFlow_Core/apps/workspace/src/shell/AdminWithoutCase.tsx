// The Admin area opened from Start with no case (ADR-114 Amendment 5 point 9): administration is the
// deployment's, not a case's, so it needs none — on a fresh install there may be none to open.
import type { ReactNode } from "react";

import { AdminPlace } from "../admin/AdminPlace";
import { Button } from "../design/primitives/Button";
import { StartBar } from "./StartPage";

export interface AdminWithoutCaseProps {
  apiBaseUrl: string;
  bearerToken: string;
  rights: ReadonlySet<string>;
  onStart: () => void;
  account: ReactNode;
}

export function AdminWithoutCase({ onStart, account, ...admin }: AdminWithoutCaseProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <StartBar account={account} onStart={onStart} />
      <div style={{ padding: "var(--sp-8) var(--sp-16) 0" }}>
        <Button onClick={onStart}>Start</Button>
      </div>
      <AdminPlace {...admin} />
    </div>
  );
}
