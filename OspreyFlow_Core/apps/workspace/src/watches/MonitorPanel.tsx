// Turn a saved pattern into a monitor — `02_GLASS_FRONTEND.md` §3.3: "A saved visual query run on
// a schedule against new data." Reuses `patterns/api.ts::listPatterns` rather than duplicating it —
// the pattern list `QueryBuilderPanel`'s own "Load" select already fetches is exactly the
// ownership-filtered population `MonitorStore.create` requires a `pattern_id` from
// (`app.py::create_monitor_route`'s own `PatternStore.get_authorized` check).
//
// Errors surface as an inline banner, not `ActionErrorOverlay` — `HotlistPanel.tsx`'s own doc
// comment has the full reasoning, identical here.
import { useEffect, useState } from "react";

import type { Monitor, MonitorScheduleInput, SavedPattern } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Panel } from "../design/primitives/Panel";
import { Select } from "../design/primitives/Select";
import { listPatterns } from "../patterns/api";
import { createMonitor, listMonitors, setMonitorSchedule } from "./api";
import { StatusBadge } from "./StatusBadge";

export interface MonitorPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** ADR-099 Amendment 3: the patterns offered are those of the case's datasets. */
  investigationId: string;
}

export function MonitorPanel({ apiBaseUrl, bearerToken, investigationId }: MonitorPanelProps) {
  const [patterns, setPatterns] = useState<SavedPattern[]>([]);
  const [selectedPatternId, setSelectedPatternId] = useState("");
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPatterns(apiBaseUrl, bearerToken, investigationId)
      .then(setPatterns)
      .catch(() => undefined);
    listMonitors(apiBaseUrl, bearerToken, investigationId)
      .then(setMonitors)
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSchedule(monitor: Monitor, every: MonitorScheduleInput["every"]): Promise<void> {
    setError(null);
    try {
      const changed = await setMonitorSchedule(apiBaseUrl, bearerToken, investigationId, monitor.id, {
        every,
        hour: monitor.hour ?? 6,
        weekday: every === "weekly" ? (monitor.weekday ?? 1) : null,
      });
      setMonitors((all) => all.map((m) => (m.id === changed.id ? changed : m)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleCreate(): Promise<void> {
    if (!selectedPatternId) return;
    setError(null);
    try {
      await createMonitor(apiBaseUrl, bearerToken, investigationId, { pattern_id: selectedPatternId });
      setMonitors(await listMonitors(apiBaseUrl, bearerToken, investigationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Panel title="Watched patterns" className="monitor-panel">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          <Select
            aria-label="Saved pattern"
            value={selectedPatternId}
            onChange={(e) => setSelectedPatternId(e.target.value)}
          >
            <option value="">Choose a saved pattern…</option>
            {patterns.map((p) => (
              <option key={p.pattern_id} value={p.pattern_id}>
                {p.name}
              </option>
            ))}
          </Select>
          <Button
            variant="primary"
            onClick={() => void handleCreate()}
            disabled={!selectedPatternId}
          >
            Turn into monitor
          </Button>
        </div>
        {error && (
          <p role="alert" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {monitors.map((monitor) => (
            <li
              key={monitor.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "var(--sp-4) 0",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <span className="value">
                {patterns.find((p) => p.pattern_id === monitor.pattern_id)?.name ??
                  monitor.pattern_id}
              </span>
              <span style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                {/* ADR-146 decision 4 (G16): run on its own schedule too, daily by default. */}
                <Select
                  aria-label={`How often ${patterns.find((p) => p.pattern_id === monitor.pattern_id)?.name ?? "this watch"} runs on its own`}
                  value={monitor.every ?? "daily"}
                  onChange={(e) => void handleSchedule(monitor, e.target.value as MonitorScheduleInput["every"])}
                >
                  <option value="daily">{`Daily at ${String(monitor.hour ?? 6).padStart(2, "0")}:00, and as data loads`}</option>
                  <option value="weekly">Weekly, and as data loads</option>
                  <option value="never">Only as data loads</option>
                </Select>
                <StatusBadge status={monitor.status ?? "active"} />
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}
