"""WS4a: each planted fault for the canvas-look comparison, at its real call site, and which cases it turns red.

Each plant is one exact replacement in one file (asserted to occur once), the comparison run once, the file restored.
"""
import pathlib
import re
import shutil
import subprocess
import sys

REPO = pathlib.Path.home() / "away-ws4a"
WS = REPO / "OspreyFlow_Core/apps/workspace"
REF = WS / "keyboard/canvas-compare"
PLANTS = [
    ("case 1: the dotted program swapped for EdgeLineProgram in GlassCanvas's program table (a dotted link drawn solid)",
     WS / "src/canvas/GlassCanvas.tsx", '          "glass-edge-dotted": DottedEdgeProgram,', '          "glass-edge-dotted": EdgeLineProgram,'),
    ("case 1b: the dashed program swapped for EdgeLineProgram (an inferred link drawn solid)",
     WS / "src/canvas/GlassCanvas.tsx", '          "glass-edge-dashed": DashedEdgeProgram,', '          "glass-edge-dashed": EdgeLineProgram,'),
    ("case 2: labelStyle.ts's label font one pixel larger",
     WS / "src/canvas/labelStyle.ts", "return `${weight} ${NODE_LABEL_SIZE}px ${literal", "return `${weight} ${NODE_LABEL_SIZE + 1}px ${literal"),
    ("case 2b: the export's watermark words changed (chartExport.ts)",
     WS / "src/export/chartExport.ts", "return `${mark.osprey_mark} · ${mark.investigation_id}", "return `${mark.osprey_mark} - ${mark.investigation_id}"),
    ("case 3: ADR-119's community links turned off at their real switch (drawsCommunityLinks, glass-shared)",
     REPO / "OspreyFlow_Core/packages/glass-shared/src/canvas/communityLinks.ts",
     '  return linkCount > COMMUNITY_LINKS_ABOVE && (band === "overview" || band === "structure");',
     '  return false && linkCount > COMMUNITY_LINKS_ABOVE && (band === "overview" || band === "structure");'),
    ("case 4: the map layer's camera sync offset by a pixel (sigmaMaplibreLayer.ts's syncMapWithSigma)",
     WS / "src/map/sigmaMaplibreLayer.ts",
     "  map.fitBounds(new LngLatBounds([geoSouthWest, geoNorthEast]), { duration: 0 });",
     "  map.fitBounds(new LngLatBounds([geoSouthWest, geoNorthEast]), { duration: 0, offset: [1, 0] });"),
    ("case 5: a tolerance of 100% (anything passes)",
     REF / "TOLERANCE.json", None, None),
    ("case 6: a reference replaced by hand (links.png overwritten with labels.png)",
     REF / "links.png", None, None),
]
only = sys.argv[1:]  # optional: plant numbers to run
for number, (name, path, old, new) in enumerate(PLANTS, 1):
    if only and str(number) not in only:
        continue
    backup = path.read_bytes()
    try:
        if old is not None:
            text = backup.decode()
            assert text.count(old) == 1, (name, text.count(old))
            path.write_text(text.replace(old, new))
        elif path.name == "TOLERANCE.json":
            path.write_text(re.sub(r'"share": [0-9.e-]+', '"share": 1', backup.decode()))
        else:
            shutil.copyfile(REF / "labels.png", path)
        p = subprocess.run(
            ["bash", str(pathlib.Path.home() / "osprey-d246/d246_ns.sh"), "env", "OSPREY_PORTS_SLOT=21", "sh", "-c",
             "cd apps/workspace && npx playwright test --config keyboard/canvas-compare.config.ts --workers=1 --reporter=line"],
            env={"REPO": str(REPO), "PATH": "/usr/bin:/bin", "HOME": str(pathlib.Path.home())}, capture_output=True, text=True)
        lines = p.stdout.splitlines()
        shares = [l.strip() for l in lines if l.strip().startswith("canvas-compare ")]
        red = sorted({m.group(1) for l in lines for m in [re.search(r"›\s+(.*?)\s*$", l)] if m and re.match(r"\s+\d+\) ", l)})
        summary = [l.strip() for l in lines if re.search(r"^\s+\d+ (passed|failed)", l)]
        print(f"PLANT {number} {name}\n  exit {p.returncode}; {summary}\n  red: {red}", flush=True)
        for s in shares:
            print(f"  {s}", flush=True)
    finally:
        path.write_bytes(backup)
print("restored:", subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True).stdout.strip() or "clean")
