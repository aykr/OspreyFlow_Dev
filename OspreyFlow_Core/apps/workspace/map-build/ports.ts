// The production-bundle run's own port (`apps/lanePorts.ts`): 5187 on main.
import { lanePort } from "../../lanePorts";

export const MAP_BUILD_PORT = lanePort(5187);
