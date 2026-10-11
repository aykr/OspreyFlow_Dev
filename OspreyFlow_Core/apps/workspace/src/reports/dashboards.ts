// Superset dashboards inside the Glass (ADR-111 Amendment 3): the Conduit lists the boards this
// person may open — only those whose every figure they could count themselves — and asks Superset
// for a short-lived guest token for one. The Glass enforces nothing; it only asks.
import type { DashboardGuestToken, EmbeddedDashboard } from "../../../../packages/schemas/generated";

export interface DashboardsApi {
  apiBaseUrl: string;
  bearerToken: string;
}

export async function listEmbeddedDashboards(api: DashboardsApi): Promise<EmbeddedDashboard[]> {
  const response = await fetch(`${api.apiBaseUrl}/v1/reports/dashboards`, {
    headers: { Authorization: `Bearer ${api.bearerToken}` },
  });
  if (response.status === 502) throw new Error("The dashboard service did not answer. Ask an administrator.");
  if (!response.ok) throw new Error(`Could not list the dashboards (${response.status}).`);
  return (await response.json()) as EmbeddedDashboard[];
}

export async function dashboardGuestToken(api: DashboardsApi, slug: string): Promise<DashboardGuestToken> {
  const response = await fetch(
    `${api.apiBaseUrl}/v1/reports/dashboards/${encodeURIComponent(slug)}/guest-token`,
    { method: "POST", headers: { Authorization: `Bearer ${api.bearerToken}` } },
  );
  if (response.status === 404) throw new Error("That dashboard is not one you may open.");
  if (response.status === 502) throw new Error("The dashboard service did not answer. Ask an administrator.");
  if (!response.ok) throw new Error(`Could not open the dashboard (${response.status}).`);
  return (await response.json()) as DashboardGuestToken;
}
