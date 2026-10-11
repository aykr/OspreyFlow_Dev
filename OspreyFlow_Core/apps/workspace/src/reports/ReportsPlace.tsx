// The Reports view (ADR-111) with its tabs: the case's own figures (always), then — each only when
// the person holds the right it rests on (ADR-112) — Trends, Packs, Published (ADR-113), and the
// Superset dashboards this person may open (Amendment 3 of ADR-111).
import { useState } from "react";

import { Tabs } from "../design/primitives/Tabs";
import { canAssemblePacks, canBuildTrends, canExportPacks, canReadPublished, type Rights } from "../rights/visibility";
import { EmbeddedDashboards, type Embed } from "./EmbeddedDashboards";
import { PacksTab } from "./PacksTab";
import { PublishedTab } from "./PublishedTab";
import { ReportsView } from "./ReportsView";
import { TrendsTab } from "./TrendsTab";

type TabId = "figures" | "trends" | "packs" | "published" | "dashboards";

export interface ReportsPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  canDownload: boolean;
  embed?: Embed;
  /** What this person may do; absent or null means not yet known, so everything is offered. */
  rights?: Rights;
  /** Receives an exported pack's print document; the default prints it from a hidden frame. */
  print?: (html: string) => void;
}

export function ReportsPlace({ embed, rights = null, print, ...props }: ReportsPlaceProps) {
  const [tab, setTab] = useState<TabId>("figures");
  const api = { apiBaseUrl: props.apiBaseUrl, bearerToken: props.bearerToken, investigationId: props.investigationId };
  const tabs: { id: TabId; label: string }[] = [
    { id: "figures", label: "Figures" },
    ...(canBuildTrends(rights) ? [{ id: "trends" as const, label: "Trends" }] : []),
    ...(canAssemblePacks(rights) ? [{ id: "packs" as const, label: "Packs" }] : []),
    ...(canReadPublished(rights) ? [{ id: "published" as const, label: "Published" }] : []),
    { id: "dashboards", label: "Dashboards" },
  ];
  // A tab the rights no longer offer falls back to Figures rather than showing a screen to be refused.
  const active: TabId = tabs.some((t) => t.id === tab) ? tab : "figures";
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ padding: "var(--sp-8) var(--sp-16) 0" }}>
        <Tabs tabs={tabs} activeId={active} onChange={(id) => setTab(id as TabId)} />
      </div>
      {active === "figures" && <ReportsView {...props} />}
      {active === "trends" && <TrendsTab api={api} canAssemble={canAssemblePacks(rights)} />}
      {active === "packs" && <PacksTab api={api} canExport={canExportPacks(rights)} print={print} />}
      {active === "published" && <PublishedTab api={api} canExport={canExportPacks(rights)} print={print} />}
      {active === "dashboards" && (
        <div style={{ flex: 1, display: "flex", padding: "var(--sp-16)", minHeight: 0 }}>
          <EmbeddedDashboards apiBaseUrl={props.apiBaseUrl} bearerToken={props.bearerToken} embed={embed} />
        </div>
      )}
    </div>
  );
}
