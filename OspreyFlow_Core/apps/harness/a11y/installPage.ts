import { lanePort } from "../../lanePorts";

// The guided install page's address and token for this directory's scans, shared by
// `playwright.config.ts` (which starts the page) and `install-page.spec.ts` (which presents the
// token as the page's cookie). Distinct from `keyboard/playwright.config.ts`'s 5192/7218, so both
// suites can run at once.
export const INSTALL_VITE_PORT = lanePort(5194); // this lane's own (T2, lane_ports.tsv)
export const INSTALL_API_PORT = String(lanePort(7220));
export const INSTALL_BASE = `http://localhost:${INSTALL_VITE_PORT}`;
export const INSTALL_TOKEN = "a11y-spec-install-token";
