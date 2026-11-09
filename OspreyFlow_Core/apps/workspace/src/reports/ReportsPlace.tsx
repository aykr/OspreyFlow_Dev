// The case's Figures (ADR-145 Amendment 4 decision 8, replacing ADR-111's Reports view) with its
// tabs: the case's own figures (always), then — each only when the person holds the right it rests
// on (ADR-112) — Trends, Packs, Published (ADR-113) and Data feeds (ADR-110 decision 9). Superset's
// boards are not here: the Glass's rail *Dashboards* is their one door (decision 8, D1).
import { useState } from "react";

import { Tabs } from "../design/primitives/Tabs";
import {
  canAssemblePacks,
  canBuildTrends,
  canExportPacks,
  canReadDataFeeds,
  canReadPublished,
  type Rights,
} from "../rights/visibility";
import { DataFeedsTab } from "./DataFeedsTab";
import { PacksTab } from "./PacksTab";
import { PublishedTab } from "./PublishedTab";
import { ReportsView, type FromAlert } from "./ReportsView";
import { TrendsTab } from "./TrendsTab";

export type TabId = "figures" | "trends" | "packs" | "published" | "feeds";

export interface ReportsPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  canDownload: boolean;
  /** Opens an alert at its address; given only when Rules and Monitoring is offered to the reader. */
  onOpenAlert?: (alertId: string) => void;
  /** Opened from an alert (the Reports Viewer's journey, ADR-145 Amendment 4 decision 10). */
  fromAlert?: FromAlert | null;
  initialWeeks?: number;
  /** What this person may do; absent or null means not yet known, so everything is offered. */
  rights?: Rights;
  /** Receives an exported pack's print document; the default prints it from a hidden frame. */
  print?: (html: string) => void;
  /** The tab to open on (ADR-128: a case brief's saved-trend attachment opens Trends). Figures when
   * left out, and Figures when the tab is one the person's rights do not offer. */
  initialTab?: TabId;
}

export function ReportsPlace({ rights = null, print, initialTab = "figures", ...props }: ReportsPlaceProps) {
  const [tab, setTab] = useState<TabId>(initialTab);
  const api = { apiBaseUrl: props.apiBaseUrl, bearerToken: props.bearerToken, investigationId: props.investigationId };
  const tabs: { id: TabId; label: string }[] = [
    { id: "figures", label: "Figures" },
    ...(canBuildTrends(rights) ? [{ id: "trends" as const, label: "Trends" }] : []),
    ...(canAssemblePacks(rights) ? [{ id: "packs" as const, label: "Packs" }] : []),
    ...(canReadPublished(rights) ? [{ id: "published" as const, label: "Published" }] : []),
    ...(canReadDataFeeds(rights) ? [{ id: "feeds" as const, label: "Data feeds" }] : []),
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
      {active === "feeds" && <DataFeedsTab api={api} />}
    </div>
  );
}
