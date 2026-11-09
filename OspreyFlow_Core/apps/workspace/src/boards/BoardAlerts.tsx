// The boards' *Alerts* panel (ADR-146 decision 9; rules-b's `reports/AlertsPanel`, mounted on a
// drawing board as the panel's own header says it would be once L3.3 built boards). The case's
// open alerts by source and age, and the newest few, as the Conduit counts them for this reader
// (rule 7). On a board it never opens an alert: the rows are words, since the board is not where an
// alert is worked. A reader the case's figures are not for is shown no panel at all.
import { useEffect, useState } from "react";

import type { MonitoringFigures } from "../../../../packages/schemas/generated";
import { fetchReport, type ReportsApi } from "../reports/api";
import { AlertsPanel } from "../reports/AlertsPanel";

/** The period the case's figures are read over: the Figures tab's own default. */
export const BOARD_ALERT_WEEKS = 12;

export function BoardAlerts({ api }: { api: ReportsApi }) {
  const [monitoring, setMonitoring] = useState<MonitoringFigures | null | "none">(null);
  useEffect(() => {
    let live = true;
    fetchReport(api, BOARD_ALERT_WEEKS)
      .then((figures) => live && setMonitoring(figures.monitoring ?? "none"))
      .catch(() => live && setMonitoring("none"));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId]);
  if (monitoring === null || monitoring === "none") return null;
  return <AlertsPanel api={api} monitoring={monitoring} />;
}
