// An alert opened at its own address (ADR-146 decision 6): `/alerts/<id>` names no case, so the
// Conduit says which case the alert is worked in (`GET /v1/alerts/{id}`), and the workspace opens
// that case on the alert. Switching case reloads the page (`investigation/cases.ts`'s `openCase`),
// so the address goes with it, with the case in the query as every case switch carries it.
import { useEffect, useState } from "react";

import type { AlertExplanation } from "../../../../packages/schemas/generated";
import { INVESTIGATION_ID_SESSION_KEY } from "../investigation/investigationId";
import { alertPath, RULES_PATH } from "../shell/router";
import { openAlertAtAddress } from "./api";

/** Said for an alert that does not exist and for one the reader may not see alike (rule 3). */
export const NO_SUCH_ALERT = "There is no alert at this address that you can see.";

export type AlertAtAddressState =
  | { status: "reading" }
  | { status: "missing" }
  | { status: "failed"; message: string }
  | { status: "found"; caseId: string; explanation: AlertExplanation };

/** The alert at the address, as the Conduit answers it for this reader; `null` for no address. */
export function useAlertAtAddress(apiBaseUrl: string, bearerToken: string, alertId: string | null): AlertAtAddressState | null {
  const [read, setRead] = useState<{ id: string; state: AlertAtAddressState } | null>(null);
  useEffect(() => {
    if (!alertId || !bearerToken) return;
    let live = true;
    openAlertAtAddress(apiBaseUrl, bearerToken, alertId)
      .then((found) => {
        if (!live) return;
        const state: AlertAtAddressState = found
          ? { status: "found", caseId: found.investigation_id, explanation: found.explanation }
          : { status: "missing" };
        setRead({ id: alertId, state });
      })
      .catch((e: Error) => live && setRead({ id: alertId, state: { status: "failed", message: e.message } }));
    return () => {
      live = false;
    };
  }, [apiBaseUrl, bearerToken, alertId]);
  if (!alertId) return null;
  return read && read.id === alertId ? read.state : { status: "reading" };
}

/** The case's page on the alert: the alert's address with the case, as `openCase` opens a case. */
export function alertInItsCaseUrl(alertId: string, caseId: string): string {
  return `${alertPath(alertId)}?investigation=${encodeURIComponent(caseId)}&from=case`;
}

/** Opens the alert's own case on the alert (a reload, as every case switch is). */
export function openAlertInItsCase(
  alertId: string,
  caseId: string,
  go: (url: string) => void = (url) => window.location.assign(url),
): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, caseId);
  go(alertInItsCaseUrl(alertId, caseId));
}

/** Opens a case on Rules and Monitoring (a reload, as every case switch is). */
export function openRulesOnCase(caseId: string, go: (url: string) => void = (url) => window.location.assign(url)): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, caseId);
  go(`${RULES_PATH}?investigation=${encodeURIComponent(caseId)}&from=case`);
}
