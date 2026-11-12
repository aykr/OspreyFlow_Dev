// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DefaultMarking = string | null;

/**
 * Declaring, changing or clearing (`None`) a source's default marking (ADR-140 Amendment 19):
 * one of the handling scheme's classifications, never above the declarer's clearance or the
 * deployment's highest marking, never below the source's own marking.
 */
export interface SourceDefaultMarkingInput {
  default_marking?: DefaultMarking;
}
