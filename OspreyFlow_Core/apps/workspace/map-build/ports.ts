// The production-bundle run's own port (`apps/lanePorts.ts`): 5189 on main. Not 5187: `deck-capture/` holds that (and 5188) as literals.
import { lanePort } from "../../lanePorts";

export const MAP_BUILD_PORT = lanePort(5189);
