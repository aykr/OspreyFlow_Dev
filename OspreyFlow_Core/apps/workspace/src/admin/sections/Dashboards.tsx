// Admin › People › Dashboard identities (ADR-111, ADR-145 decision 5): register a dashboard's
// identity, see how fresh its figures are, remove one. Behind `manage_dashboards`.
import { useEffect, useState } from "react";

import type { DashboardIdentity } from "../../../../../packages/schemas/generated";
import { Button, Input, Select } from "../../design/primitives";
import { dashboardsSignInKind, listDashboards, registerDashboard, removeDashboard, type AdminApi } from "../api";

const utc = (iso: string) => `${iso.slice(0, 16).replace("T", " ")} UTC`;

/** ADR-148 Amendment 10: on Entra ID the dashboard's own app registration holds its secret, and needs
 * this API's application permission before its token is a dashboard's. */
export const ENTRA_DASHBOARD_ROLE = "Dashboard.Read";
const entraRegistered = (applicationId: string) =>
  `${applicationId} is registered. Its secret stays with its app registration in Entra ID. Ask your Entra ` +
  `administrator to grant that registration this API's ${ENTRA_DASHBOARD_ROLE} application permission (with ` +
  "admin consent), then give the report sync its application id and secret.";

/** How fresh a dashboard's figures are, from the reporting mart (ADR-111 Amendment 2): a standing
 * failure first, in the sync service's own words; then the last good pull; else never pulled. */
export function feedFreshness(d: DashboardIdentity): { text: string; failing: boolean } {
  const cases = d.cases_pulled ?? 0;
  if (d.last_failure && d.failed_at) {
    const last = d.last_pulled ? `; last good pull ${utc(d.last_pulled)}` : "; never pulled";
    return { text: `Failing since ${utc(d.failed_at)}: ${d.last_failure}${last}`, failing: true };
  }
  if (d.last_pulled) {
    return { text: `Pulled ${utc(d.last_pulled)} · ${cases} ${cases === 1 ? "case" : "cases"}`, failing: false };
  }
  return { text: "Never pulled: no case has given it Viewer yet", failing: false };
}

export function Dashboards({ api }: { api: AdminApi }) {
  const [dashboards, setDashboards] = useState<DashboardIdentity[] | null>(null);
  const [levels, setLevels] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [clearance, setClearance] = useState("");
  const [unit, setUnit] = useState("");
  const [secret, setSecret] = useState<{ clientId: string; value: string } | null>(null);
  const [entra, setEntra] = useState(false);
  const [applicationId, setApplicationId] = useState("");
  const [registered, setRegistered] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    listDashboards(api).then(setDashboards).catch((e: Error) => setProblem(e.message));
    dashboardsSignInKind(api)
      .then((k) => setEntra(k.kind === "entra"))
      .catch(() => setEntra(false));
    fetch(`${api.apiBaseUrl}/v1/handling-scheme`, { headers: { Authorization: `Bearer ${api.bearerToken}` } })
      .then((r) => (r.ok ? r.json() : { classification: [] }))
      .then((scheme: { classification?: string[] }) => {
        setLevels(scheme.classification ?? []);
        setClearance((scheme.classification ?? [])[0] ?? "");
      })
      .catch(() => setLevels([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);

  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        A dashboard reads the reporting feed as an identity of its own. Register it here; a case's Author then gives its account
        Viewer on that case, as for a person. It cannot read above your own clearance.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {registered && (
        <div role="status" style={{ border: "1px solid var(--warning)", padding: "var(--sp-8)" }}>
          <p style={{ margin: 0 }}>{entraRegistered(registered)}</p>
        </div>
      )}
      {secret && (
        <div role="status" style={{ border: "1px solid var(--warning)", padding: "var(--sp-8)" }}>
          <p style={{ margin: 0 }}>{`${secret.clientId} is registered. Its secret is shown once — copy it into the dashboard's settings now:`}</p>
          <code>{secret.value}</code>
        </div>
      )}
      <table className="table" aria-label="Dashboard identities">
        <thead>
          <tr>
            <th>Dashboard</th>
            <th>Account (give this to a case's Author)</th>
            <th>Reads at</th>
            <th>Figures</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(dashboards ?? []).map((d) => (
            <tr key={d.client_id}>
              <td>{d.client_id}</td>
              <td><code>{d.account_id}</code></td>
              <td>{`${d.clearance ?? "—"} · ${d.org_unit ?? "—"}`}</td>
              <td style={feedFreshness(d).failing ? { color: "var(--error)" } : undefined}>{feedFreshness(d).text}</td>
              <td>
                <Button
                  aria-label={`Remove ${d.client_id}`}
                  onClick={() =>
                    void removeDashboard(api, d.client_id)
                      .then(() => setDashboards((dashboards ?? []).filter((x) => x.client_id !== d.client_id)))
                      .catch((e: Error) => setProblem(e.message))
                  }
                >
                  Remove
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {dashboards?.length === 0 && <p className="label" style={{ margin: 0 }}>No dashboard is registered.</p>}
      <form
        aria-label="Register a dashboard"
        onSubmit={(e) => {
          e.preventDefault();
          setProblem(null);
          void registerDashboard(api, name.trim(), clearance, unit.trim(), entra ? applicationId.trim() : undefined)
            .then((made) => {
              if (made.secret) setSecret({ clientId: made.dashboard.client_id, value: made.secret });
              else setRegistered(made.dashboard.client_id);
              setApplicationId("");
              setDashboards([...(dashboards ?? []), made.dashboard]);
              setName("");
            })
            .catch((err: Error) => setProblem(err.message));
        }}
        style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 420, border: "1px solid var(--border-subtle)", padding: "var(--sp-12)" }}
      >
        <h2 className="value" style={{ margin: 0 }}>Register a dashboard</h2>
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          Name
          <Input aria-label="Dashboard name" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          Reads at clearance
          <Select aria-label="Dashboard reads at clearance" value={clearance} onChange={(e) => setClearance(e.target.value)}>
            {levels.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </Select>
        </label>
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          Unit
          <Input aria-label="Dashboard unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
        </label>
        {entra && (
          <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            Application id (its app registration in Entra ID)
            <Input aria-label="Dashboard application id" value={applicationId} onChange={(e) => setApplicationId(e.target.value)} />
          </label>
        )}
        <Button type="submit" variant="primary" disabled={!name.trim() || !clearance || !unit.trim() || (entra && !applicationId.trim())}>
          Register
        </Button>
      </form>
    </>
  );
}
