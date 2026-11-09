// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Region = string;

/**
 * `POST /v1/admin/geospatial/build-basemap`: a named region only. The tiles folder and the
 * planetiler jar are the deployment's own, never a path typed in the Glass.
 */
export interface BuildBasemapInput {
  region: Region;
}
