// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * Items moved on the board (by drag or by arrow keys): the board's own layout, not data.
 */
export interface BoardMove {
  positions: Positions;
}
export interface Positions {
  [k: string]: {
    [k: string]: number;
  };
}
