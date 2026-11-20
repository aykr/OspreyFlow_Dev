// The bearer token the map-tiles harness gives the Map view and `map-tiles.spec.ts`'s route requires on
// every read of the archive, as the Conduit's `local-source` route requires one (`src/map/pmtilesAuth.ts`).
// Not a credential: an invented string that only this fixture knows. Its own file because the harness
// runs in the browser and `mapTilesFixture.ts` imports Node's `fs`.
export const FIXTURE_BEARER_TOKEN = "gg6-fixture-token";
