// The *Monitoring* place on the left rail (`06_DECISIONS.md` ADR-133 decision 5; ADR-109 ruling 5
// before it, as *Alerts*): the one alert queue first — every kind the reader may see — then the
// rules that raise alerts and their templates, the reader's own hotlists and watched patterns with
// their alert inbox, the rows a failing rule held, and the rule audit; and, since ADR-133 stage (c),
// the screening lists. Since the owner's answer of 1 November 2026 the Watches tab is the only way
// to the watches: the left rail's Watches entry is gone.
// What each account may do follows its level in the case, read as every other case surface reads
// it (`listCases`); the Conduit refuses whatever a stale view offers anyway.
import { useEffect, useState } from "react";
import { Tabs } from "../design/primitives";
import { listCases, type AccessLevel } from "../investigation/cases";
import { AlertQueue } from "./AlertQueue";
import type { CanvasOutcome } from "./api";
import { HeldRowsPanel } from "./HeldRowsPanel";
import { ListsPanel } from "./ListsPanel";
import { RuleAuditPanel } from "./RuleAuditPanel";
import { RulesPanel } from "./RulesPanel";
import type { EdgeTypeDef, EntityTypeDef } from "../../../../packages/schemas/generated";
import { StrengthPanel } from "../strength/StrengthPanel";
import { AlertInbox } from "../watches/AlertInbox";
import { HotlistPanel } from "../watches/HotlistPanel";
import { MonitorPanel } from "../watches/MonitorPanel";

export interface AlertsPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string | null;
  accountId: string | null;
  isAdministrator: boolean;
  /** ADR-112's `load_screening_lists`: subscribing to and refreshing a screening list. */
  canManageLists?: boolean;
  onCanvas: (outcome: CanvasOutcome, nodeIds: string[]) => void;
  /** The alert inbox's jump: the new investigation an alert was branched into, opened. */
  onOpenInvestigation?: (investigationId: string) => void;
  /** ADR-139: `manage_strength_influencers`, so the installation-wide influencers are offered. */
  canManageInfluencers?: boolean;
  /** The ontology's types, for the influencer editor's closed choices. */
  entityTypes?: readonly EntityTypeDef[];
  edgeTypes?: readonly EdgeTypeDef[];
  /** Told when the influencers in force may have changed (the legend is read again). */
  onInfluencersChanged?: () => void;
}

type Tab = "queue" | "rules" | "watches" | "lists" | "strength" | "held" | "audit";

export function AlertsPlace(props: AlertsPlaceProps) {
  const { apiBaseUrl, bearerToken, investigationId } = props;
  const [tab, setTab] = useState<Tab>("queue");
  const [level, setLevel] = useState<AccessLevel | null>(null);

  useEffect(() => {
    if (!investigationId) return;
    let cancelled = false;
    listCases(apiBaseUrl, bearerToken)
      .then((cases) => {
        if (!cancelled) setLevel(cases.find((c) => c.id === investigationId)?.level ?? null);
      })
      .catch(() => !cancelled && setLevel(null));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  if (!investigationId) return <p className="label">Open a case to see its alerts and watches.</p>;
  const api = { apiBaseUrl, bearerToken, investigationId };
  const readsAudit = level === "author" || props.isAdministrator;
  const tabs = [
    { id: "queue", label: "Queue" },
    { id: "rules", label: "Rules" },
    { id: "watches", label: "Watches" },
    { id: "lists", label: "Lists" },
    // ADR-139 decision 3: what makes a link strong in this case, and who may change it.
    { id: "strength", label: "Connection strength" },
    ...(level === "editor" || level === "author" ? [{ id: "held", label: "Held rows" }] : []),
    ...(readsAudit ? [{ id: "audit", label: "Audit" }] : []),
  ];

  return (
    <section aria-label="Monitoring" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", padding: "var(--sp-16)", minHeight: 0, flex: 1, overflowY: "auto" }}>
      <h2 className="value" style={{ margin: 0 }}>Monitoring</h2>
      <Tabs tabs={tabs} activeId={tab} onChange={(id) => setTab(id as Tab)} />
      {tab === "queue" && <AlertQueue {...api} level={level} accountId={props.accountId} onCanvas={props.onCanvas} />}
      {tab === "rules" && <RulesPanel {...api} level={level} isAdministrator={props.isAdministrator} accountId={props.accountId} />}
      {tab === "watches" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", maxWidth: 640 }}>
          <HotlistPanel {...api} />
          <MonitorPanel {...api} />
          <AlertInbox {...api} onOpenInvestigation={props.onOpenInvestigation ?? (() => undefined)} />
        </div>
      )}
      {tab === "lists" && (
        <ListsPanel apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} canManage={props.canManageLists ?? false} />
      )}
      {tab === "strength" && (
        <StrengthPanel
          {...api}
          accountId={props.accountId}
          canManage={props.canManageInfluencers ?? false}
          entityTypes={props.entityTypes ?? []}
          edgeTypes={props.edgeTypes ?? []}
          onChanged={props.onInfluencersChanged}
        />
      )}
      {tab === "held" && <HeldRowsPanel {...api} level={level} />}
      {tab === "audit" && readsAudit && <RuleAuditPanel {...api} />}
    </section>
  );
}
