// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type CellId = string;
export type CentroidLon = number;
export type CentroidLat = number;
export type Count = number;

export interface GeoBin {
  cell_id: CellId;
  centroid_lon: CentroidLon;
  centroid_lat: CentroidLat;
  count: Count;
  [k: string]: unknown;
}
