// The Admin area's keyboard harness (ADR-110 Amendment 1, ADR-112, `CLAUDE.md` rule 13): its own
// surface, its own registry (`ADMIN_ACTIONS`). Every call is intercepted by `admin.spec.ts`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { AdminPlace } from "../src/admin/AdminPlace";

const tab = new URLSearchParams(location.search).get("rights") ?? "manage_people,manage_dashboards,administer_system";
const open = new URLSearchParams(location.search).get("open");

// `?open=connections` (ADR-140 Amendment 4): for the every-harness axe scan, the page serves the
// Connections tab's list itself and opens the tab. Synthetic (rule 9). Without it, `admin.spec.ts`
// intercepts every call as before.
if (open === "connections") {
  window.fetch = async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    const body =
      path === "/v1/admin/connections"
        ? [
            { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "2026-11-01T00:00:00Z" },
            { id: "c2", kind: "files", name: "Second folder", created_by: "admin-1", created_at: "2026-11-05T00:00:00Z" },
          ]
        : [];
    return new Response(JSON.stringify(body), { status: 200 });
  };
}

createRoot(document.getElementById("root")!).render(
  <AdminPlace apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" rights={new Set(tab.split(","))} />,
);

if (open) {
  for (let i = 0; i < 40; i++) {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button[role=tab]")].find((b) => b.textContent === "Connections");
    if (button) {
      button.click();
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}
