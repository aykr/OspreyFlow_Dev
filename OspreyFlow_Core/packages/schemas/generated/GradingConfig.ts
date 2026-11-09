// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Default: 5x5x5. The scheme drawn items are graded in: 5x5x5; 3x5x2, whose handling code (P or C) is part of the grade and never merged with the marking; or the path of a scheme file (.yaml, beside this file unless absolute) naming its own scheme and each part's grades.
 */
export type Scheme = string;

/**
 * The deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11 and Amendment 6): the
 * scheme every drawn node and link is graded in, chosen at install (`install.yaml`'s
 * `grading.scheme`) and shown read-only in Admin. Changed only by `ospreyflow grading change`
 * (C13), which changes the items and this setting together: editing this alone would leave the
 * items' grades in the old scheme.
 */
export interface GradingConfig {
  scheme?: Scheme;
}
