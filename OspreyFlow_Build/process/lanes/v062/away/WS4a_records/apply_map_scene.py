"""WS4a: the comparison's map scene, a shared settled-picture helper and a renderer check of the spec's own."""
import pathlib

WS = pathlib.Path.home() / "away-ws4a/OspreyFlow_Core/apps/workspace"
spec = WS / "keyboard/canvas-compare.spec.ts"
t = spec.read_text()


def sub(old, new):
    global t
    assert t.count(old) == 1, old
    t = t.replace(old, new)


sub('import { layoutSettled } from "./layoutSettled";\n',
    'import { layoutSettled } from "./layoutSettled";\nimport { FIXTURE_FILE } from "./mapTilesFixture";\nimport { FIXTURE_BEARER_TOKEN } from "./mapTilesToken";\n')
sub('''  /** The harness's scene. */
  scene: string;''', '''  /** The harness's scene (`canvas-compare-harness.tsx`); none for the map. */
  scene?: string;
  /** The Map view on GG6's synthetic tiles (`map-tiles-harness.tsx`) in place of the graph canvas. */
  map?: boolean;''')
sub('''  { name: "communities", scene: "communities" },
];''', '''  { name: "communities", scene: "communities" },
  // The Map view: MapLibre on GG6's synthetic PMTiles archive with the canvas's Sigma layer over it
  // (`sigmaMaplibreLayer.ts`).
  { name: "map", map: true },
];''')
# The renderer check, of the spec's own, so the map's page needs nothing of the comparison's harness.
sub('''  // The references belong to one renderer (pixels differ between graphics stacks): drawn with another, this machine
  // cannot judge the look against them, and says so rather than reporting a changed look.
  const renderer = await page.evaluate(() => window.__COMPARE__!.renderer);
  if (WRITING) writeFileSync(new URL("renderer.txt", FOLDER), `${renderer}\\n`);
  else {
    const made = readReferences([]).record?.machine?.webgl;
    expect(renderer, `the references were made with the WebGL renderer ${made}; make a set of this machine's own to compare here`).toBe(made);
  }
''', '''  await checkRenderer(page);
''')
sub('''/** Draws `c` and returns its picture as PNG bytes. */''', '''/** The references belong to one WebGL renderer (pixels differ between graphics stacks): drawn with another, this
 * machine cannot judge the look against them, and says so rather than reporting a changed look. Writing, it records
 * the renderer for the command (`renderer.txt`). */
async function checkRenderer(page: Page): Promise<void> {
  const renderer = await page.evaluate(() => {
    const gl = document.createElement("canvas").getContext("webgl");
    if (!gl) return "no WebGL";
    const named = gl.getExtension("WEBGL_debug_renderer_info");
    return String(named ? gl.getParameter(named.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
  });
  if (WRITING) writeFileSync(new URL("renderer.txt", FOLDER), `${renderer}\\n`);
  else {
    const made = readReferences([]).record?.machine?.webgl;
    expect(renderer, `the references were made with the WebGL renderer ${made}; make a set of this machine's own to compare here`).toBe(made);
  }
}

/** The picture inside `box` once it has stopped changing: two alike, half a second apart. A node's drawing
 * (`@sigma/node-image`) arrives a frame or more after the node, and a map's tiles after its style. */
async function settledShot(page: Page, box: { x: number; y: number; width: number; height: number }, name: string): Promise<Buffer> {
  const shot = () => page.screenshot({ clip: box, animations: "disabled", caret: "hide" });
  let last = await shot();
  for (let i = 0; i < 20; i++) {
    await page.waitForTimeout(500);
    const now = await shot();
    if (now.equals(last)) return now;
    last = now;
  }
  throw new Error(`the ${name} scene never stopped changing`);
}

/** Draws `c` and returns its picture as PNG bytes. */''')
sub('''  await page.goto(`/keyboard/canvas-compare-harness.html?scene=${c.scene}`);''',
    '''  if (c.map) return drawMap(page);
  await page.goto(`/keyboard/canvas-compare-harness.html?scene=${c.scene}`);''')
# The canvas scenes use the shared helper; the export follows the settled picture.
start = t.index("  // The picture once it has stopped changing:")
end = t.index("  throw new Error(`the ${c.name} scene never stopped changing`);\n}\n") + len(
    "  throw new Error(`the ${c.name} scene never stopped changing`);\n}\n")
export_start = t.index("      const base64 = await page.evaluate(async () => {", start)
export_end = t.index("      return Buffer.from(base64, \"base64\");\n", start) + len("      return Buffer.from(base64, \"base64\");\n")
export_block = "\n".join(line[4:] for line in t[export_start:export_end].rstrip("\n").split("\n"))
t = t[:start] + "  const picture = await settledShot(page, box, c.name);\n  if (!c.exported) return picture;\n" + export_block + "\n}\n" + t[end:]
map_code = (pathlib.Path.home() / "ws4a-tools/pending/map-scene.ts").read_text()
map_code = map_code.replace("  await page.goto(\"/keyboard/map-tiles-harness.html\");\n",
                            "  await page.goto(\"/keyboard/map-tiles-harness.html\");\n  await checkRenderer(page);\n")
sub("const tolerance = JSON.parse(", map_code + "\nconst tolerance = JSON.parse(")
spec.write_text(t)

harness = WS / "keyboard/canvas-compare-harness.tsx"
h = harness.read_text()
for old in ['''      /** The browser's WebGL renderer, as it names itself: the references belong to one. */
      renderer: string;
''', '''/** The WebGL renderer this browser draws with (SwiftShader, a GPU's own name, ...). */
function webglRenderer(): string {
  const gl = document.createElement("canvas").getContext("webgl");
  if (!gl) return "no WebGL";
  const named = gl.getExtension("WEBGL_debug_renderer_info");
  return String(named ? gl.getParameter(named.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
}''', '''  renderer: webglRenderer(),
''']:
    assert h.count(old) == 1, old
    h = h.replace(old, "")
harness.write_text(h)
print("applied")
