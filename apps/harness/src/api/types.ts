// `OspreyConfig` and its own sections are re-exported from the generated schema, never
// hand-written here — `CLAUDE.md`'s own Conventions: "TypeScript types are generated from
// [the Pydantic models]; drift is a build failure." `packages/schemas/generated/index.ts`'s own
// barrel does not re-export `Profile`/`GraphStore`/`AnalyticsEngine` (each collides with an
// unrelated type of the same bare name generated from a different Pydantic module), so these come
// from `OspreyConfig.ts` directly — `apps/workspace/src/watches/StatusBadge.tsx` already
// establishes this as the way to reach a type the barrel does not carry.
export type {
  AnalyticsEngine,
  ComponentsConfig,
  GraphStore,
  ModelsConfig,
  OspreyConfig,
  Profile,
} from "../../../../packages/schemas/generated/OspreyConfig";

// The two response shapes below are `harness/screens.py`'s own plain dataclasses, not Pydantic
// models — `generate_ts.py` only reads `schemas.deployment.ALL_MODELS`, so these are hand-written,
// kept intentionally small and matched field-for-field against `harness/webapp.py`'s own
// `_footprint_json`/`_consequences_json`.
export interface ProfileOptions {
  label: string;
  machines: string;
  memory_gb_floor: number;
  orchestrator: string;
  allowed_graph_stores: string[];
  allowed_analytics_engines: string[];
}

export interface Consequences {
  profile: string;
  machines: string;
  memory_gb_floor: number;
  orchestrator: string;
  graph_store: string;
  analytics_engine: string;
  egress_exception: boolean;
  egress_detail: string | null;
}
