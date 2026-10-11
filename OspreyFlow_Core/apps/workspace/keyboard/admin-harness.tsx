// The Admin area's keyboard harness (ADR-110 Amendment 1, ADR-112, `CLAUDE.md` rule 13): its own
// surface, its own registry (`ADMIN_ACTIONS`). Every call is intercepted by `admin.spec.ts`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { AdminPlace } from "../src/admin/AdminPlace";

const tab = new URLSearchParams(location.search).get("rights") ?? "manage_people,manage_dashboards,administer_system";

createRoot(document.getElementById("root")!).render(
  <AdminPlace apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" rights={new Set(tab.split(","))} />,
);
