// The Superset dashboards this person may open, drawn inside the Glass (ADR-111 Amendment 3) — in
// the Reports view's Dashboards tab and in the Dashboards place. Superset draws the board in a frame;
// the token it is given is read-only, lasts five minutes, is fetched again before it lapses, and
// carries the dashboard identity's rows only. ADR-111 Amendment 4: Superset draws it in the Glass's own
// look — its light and dark themes are generated from tokens.css — in whichever mode the Glass is
// showing, and follows a switch while the board is open; the Glass names the board, so Superset's own
// title and each chart's menu are hidden.
import { embedDashboard } from "@superset-ui/embedded-sdk";
import { useEffect, useRef, useState } from "react";

import type { EmbeddedDashboard } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { currentTheme, onThemeChange, type Theme } from "../theme/theme";
import { type DashboardsApi, dashboardGuestToken, listEmbeddedDashboards } from "./dashboards";

/** Superset's name for each of the Glass's modes: its light theme is `default`. */
type ThemeMode = "dark" | "default";
const themeMode = (theme: Theme): ThemeMode => (theme === "light" ? "default" : "dark");

/** The SDK's call, injectable so a test sees exactly what it was asked to mount. */
export type Embed = (options: {
  id: string;
  supersetDomain: string;
  mountPoint: HTMLElement;
  fetchGuestToken: () => Promise<string>;
  dashboardUiConfig?: {
    hideTitle?: boolean;
    hideChartControls?: boolean;
    filters?: { expanded?: boolean };
    urlParams?: { themeMode?: ThemeMode };
  };
}) => Promise<{ setThemeMode?: (mode: ThemeMode) => void } | unknown>;

export function EmbeddedDashboards({ embed = embedDashboard as Embed, ...api }: DashboardsApi & { embed?: Embed }) {
  const [boards, setBoards] = useState<EmbeddedDashboard[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const mount = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    listEmbeddedDashboards(api)
      .then((found) => {
        if (cancelled) return;
        setBoards(found);
        setOpen((current) => current ?? found[0]?.slug ?? null);
      })
      .catch((e: Error) => !cancelled && setProblem(e.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);

  useEffect(() => {
    const point = mount.current;
    if (!open || !point) return;
    let cancelled = false;
    let stopFollowing: (() => void) | undefined;
    setProblem(null);
    point.replaceChildren();
    dashboardGuestToken(api, open)
      .then((first) => {
        if (cancelled) return undefined;
        return embed({
          id: first.uuid,
          supersetDomain: first.superset_origin,
          mountPoint: point,
          // The SDK asks again before the five minutes run out; each answer is the Conduit's.
          fetchGuestToken: async () => (await dashboardGuestToken(api, open)).token,
          dashboardUiConfig: {
            hideTitle: true,
            hideChartControls: true,
            filters: { expanded: false },
            urlParams: { themeMode: themeMode(currentTheme()) },
          },
        });
      })
      .then((board) => {
        const setThemeMode = (board as { setThemeMode?: (mode: ThemeMode) => void } | undefined)?.setThemeMode;
        if (cancelled || typeof setThemeMode !== "function") return;
        // The mode may have changed while the board loaded; then every later switch.
        setThemeMode(themeMode(currentTheme()));
        stopFollowing = onThemeChange((theme) => setThemeMode(themeMode(theme)));
      })
      .catch((e: Error) => !cancelled && setProblem(e.message));
    return () => {
      cancelled = true;
      stopFollowing?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, api.apiBaseUrl, api.bearerToken]);

  return (
    <section aria-label="Dashboards" style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--sp-8)", minHeight: 0 }}>
      {boards && boards.length > 1 && (
        <div role="group" aria-label="Choose a dashboard" style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
          {boards.map((b) => (
            <Button key={b.slug} aria-pressed={b.slug === open} variant={b.slug === open ? "primary" : "default"}
                    onClick={() => setOpen(b.slug)}>
              {b.title}
            </Button>
          ))}
        </div>
      )}
      {boards && boards.length === 1 && <h3 style={{ margin: 0 }}>{boards[0]!.title}</h3>}
      {boards === null && !problem && <p className="label">Finding your dashboards…</p>}
      {boards && boards.length === 0 && (
        <p className="label" style={{ margin: 0 }}>
          No dashboard you may open. One appears here once an administrator registers it and a case&apos;s
          Author gives it Viewer on cases you can open — and only if you could count every figure it shows.
        </p>
      )}
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      <div ref={mount} className="embedded-dashboard" data-open={open ?? ""} style={{ flex: 1, minHeight: 480 }} />
    </section>
  );
}
