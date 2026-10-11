// The Reports view (ADR-111) with its two tabs (Amendment 3): the case's own figures, counted for
// the reader, and the Superset dashboards this person may open.
import { useState } from "react";

import { Tabs } from "../design/primitives/Tabs";
import { EmbeddedDashboards, type Embed } from "./EmbeddedDashboards";
import { ReportsView } from "./ReportsView";

export interface ReportsPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  canDownload: boolean;
  embed?: Embed;
}

export function ReportsPlace({ embed, ...props }: ReportsPlaceProps) {
  const [tab, setTab] = useState<"figures" | "dashboards">("figures");
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ padding: "var(--sp-8) var(--sp-16) 0" }}>
        <Tabs
          tabs={[
            { id: "figures", label: "Figures" },
            { id: "dashboards", label: "Dashboards" },
          ]}
          activeId={tab}
          onChange={(id) => setTab(id as "figures" | "dashboards")}
        />
      </div>
      {tab === "figures" && <ReportsView {...props} />}
      {tab === "dashboards" && (
        <div style={{ flex: 1, display: "flex", padding: "var(--sp-16)", minHeight: 0 }}>
          <EmbeddedDashboards apiBaseUrl={props.apiBaseUrl} bearerToken={props.bearerToken} embed={embed} />
        </div>
      )}
    </div>
  );
}
