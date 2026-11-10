// This suite's vite port, shared by `playwright.config.ts` (which serves on it) and the specs that
// name the harness's own origin, so neither can drift from the other (T2, `apps/lanePorts.ts`).
import { lanePort } from "../../lanePorts";

/** 5185 on main; this run's lane's own otherwise. */
export const KEYBOARD_PORT = lanePort(5185);
