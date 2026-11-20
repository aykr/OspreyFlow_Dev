// ADR-014 Amendment 2: the MapLibre worker is the Glass's own file, and a file a module worker will load.
import { describe, expect, it, vi } from "vitest";

import product from "../../vite.config";

const setWorkerUrl = vi.fn();
vi.mock("maplibre-gl", () => ({ setWorkerUrl }));

describe("selfHostMaplibreWorker", () => {
  it("gives MapLibre the address of the worker file the build emits, once", async () => {
    const { selfHostMaplibreWorker } = await import("./maplibreWorker");
    selfHostMaplibreWorker();
    selfHostMaplibreWorker();
    expect(setWorkerUrl).toHaveBeenCalledTimes(1);
    expect(setWorkerUrl.mock.calls[0]![0]).toMatch(/maplibre-gl-worker.*\.m?js/);
  });
});

describe("the production build's asset names", () => {
  // A module worker is refused unless the server says JavaScript, and the deployed image's nginx
  // (1.30, stock `mime.types`) serves `.mjs` as `application/octet-stream`: with the file left as
  // `maplibre-gl-worker.mjs` the map drew nothing, measured in a browser on 18 November 2026. The
  // dev server and `vite preview` both know `.mjs`, so `map-tiles.spec.ts` cannot see this.
  const config = (typeof product === "function" ? product({ command: "build", mode: "production" } as never) : product) as {
    build: { rollupOptions: { output: { assetFileNames: (asset: { names: string[] }) => string } } };
  };
  const name = config.build.rollupOptions.output.assetFileNames;

  it("emits the MapLibre worker as a .js file", () => {
    expect(name({ names: ["maplibre-gl-worker.mjs"] })).toBe("assets/[name]-[hash].js");
  });

  it("leaves every other asset with its own extension", () => {
    expect(name({ names: ["logo.svg"] })).toBe("assets/[name]-[hash][extname]");
    expect(name({ names: ["maplibre-gl.css"] })).toBe("assets/[name]-[hash][extname]");
  });
});
