"""WS4a: the export scene alone with the watermark plant, its picture kept for a look."""
import pathlib
import subprocess

REPO = pathlib.Path.home() / "away-ws4a"
f = REPO / "OspreyFlow_Core/apps/workspace/src/export/chartExport.ts"
backup = f.read_text()
old = "return `${mark.osprey_mark} · ${mark.investigation_id}"
assert backup.count(old) == 1
try:
    f.write_text(backup.replace(old, "return `PLANTED PLANTED PLANTED ${mark.investigation_id}"))
    p = subprocess.run(
        ["bash", str(pathlib.Path.home() / "osprey-d246/d246_ns.sh"), "env", "OSPREY_PORTS_SLOT=21", "sh", "-c",
         "cd apps/workspace && npx playwright test --config keyboard/playwright.config.ts keyboard/canvas-compare.spec.ts "
         "--workers=1 --reporter=line -g 'export scene' --output=/home/ospreyflow_build/ws4a-tools/pw-out"],
        env={"REPO": str(REPO), "PATH": "/usr/bin:/bin", "HOME": str(pathlib.Path.home())}, capture_output=True, text=True)
    print("\n".join(l for l in p.stdout.splitlines() if "canvas-compare" in l or "passed" in l or "failed" in l))
finally:
    f.write_text(backup)
