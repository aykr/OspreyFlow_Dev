// This suite's ports, shared by `playwright.config.ts` (which starts its servers on them) and the
// specs that name an address directly, so neither can drift from the other (T2, `apps/lanePorts.ts`).
// On main: 5191 and 7217 for the console, 5192 and 7218 for the guided install page.
import { lanePort } from "../../lanePorts";

export const VITE_PORT = lanePort(5191);
export const API_PORT = String(lanePort(7217));
export const INSTALL_VITE_PORT = lanePort(5192);
export const INSTALL_API_PORT = String(lanePort(7218));
