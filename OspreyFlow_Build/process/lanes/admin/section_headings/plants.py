"""The section headings step's plants (ADR-145 Amendment 16, rule 15): each check in
keyboard/admin-sections-look.spec.ts planted alone in the shape main drew or a regression would take, run, and the
tree restored from git. A plant counts as red only when every failure stopped at the assertion it names.

Run from the repository root, with OSPREY_PORTS_SLOT set:
python OspreyFlow_Build/process/lanes/admin/section_headings/plants.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WS = ROOT / "OspreyFlow_Core/apps/workspace"
CSS = "src/admin/admin.css"
SPEC = "keyboard/admin-sections-look.spec.ts"

# name, [(file, old, new)], spec files, -g filter, the assertion it must fail (a regex over the spec line the
# failure stopped at).
PLANTS = [
    ("Datasets' Authors an h5 again, as main had it", [("src/admin/sections/Datasets.tsx", "<h3 style={{ margin: 0 }}>Authors</h3>", "<h5 style={{ margin: 0 }}>Authors</h5>")],
     [SPEC], "Datasets in", r"expect\(skips\)"),
    ("Roles' form title an h3 again, as main had it", [("src/admin/sections/Roles.tsx", "<h2 style={{ margin: 0 }}>{title}</h2>", "<h3 style={{ margin: 0 }}>{title}</h3>")],
     [SPEC], "Roles in", r"expect\(skips\)"),
    ("the sections' h2s at the browser's size", [(CSS, ".admin-place__section h2 { font-size: var(--fs-13);", ".admin-place__section h2 { font-size: 1.5em;")],
     [SPEC], "dark look|light look", r"h\.size >= h1"),
    ("the row links without govuk-link under GOV.UK", [("src/admin/sections/People.tsx", '"admin-row-actions__link govuk-link"', '"admin-row-actions__link"')],
     [SPEC], "link focus", r"toContain\(\"govuk-link\"\)"),
    ("a local focus rule over GOV.UK's, the class kept", [(CSS, ".admin-row-actions__link[aria-expanded=\"true\"] { font-weight: 700; }", ".admin-row-actions__link[aria-expanded=\"true\"] { font-weight: 700; }\n.admin-place .admin-row-actions__link:focus { background: none; }")],
     [SPEC], "link focus", r"rgb\(255, 221, 0\)"),
]


def run(specs, grep):
    out = subprocess.run(
        ["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", *specs, "-g", grep, "--reporter=line"],
        cwd=WS, capture_output=True, text=True,
    ).stdout
    keep = [l for l in out.splitlines() if re.match(r"\s+\d+\) |\s+> \d+ \||\s+(Expected|Received)|\s+[-+] |\s+\d+ (passed|failed)", l)]
    return out, keep


def red_for_its_reason(out: str, why: str) -> tuple[bool, str]:
    """Red only when every failure stopped at the plant's own assertion. Each failure's block names the spec line
    it stopped at (`at <spec>:<line>:<col>`, present even where Playwright prints no code frame); that line of the
    spec, read from disk, must match `why`."""
    blocks = re.split(r"^\s+\d+\) ", out, flags=re.M)[1:]
    if not blocks:
        return False, "GREEN - the check misses it"
    off = []
    for block in blocks:
        at = re.search(r"at (\S+\.spec\.ts):(\d+):\d+", block)
        line = Path(at.group(1)).read_text().splitlines()[int(at.group(2)) - 1].strip() if at else "(no spec line)"
        if not re.search(why, line):
            off.append(line)
    if off:
        return False, f"red for another reason ({len(blocks)} failed; stopped at: {off})"
    return True, f"RED at its assertion in {len(blocks)} test(s)"


def main() -> int:
    missed = 0
    # The orchestrator's registry change (registry-govuk.diff) is applied in the run copy, as for the gates.
    if subprocess.run(["git", "diff", "--quiet", "--", "OspreyFlow_Core", ":!OspreyFlow_Core/apps/workspace/keyboard/actionRegistry.ts"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    for name, edits, specs, grep, why in PLANTS:
        touched = set()
        for f, old, new in edits:
            p = WS / f
            s = p.read_text()
            assert s.count(old) == 1, (name, f, old)
            p.write_text(s.replace(old, new))
            touched.add(f)
        try:
            out, keep = run(specs, grep)
        finally:
            subprocess.run(["git", "checkout", "--", *touched], cwd=WS, check=True)
        red, said = red_for_its_reason(out, why)
        missed += not red
        print(f"== {name} (must fail at /{why}/): {said}")
        print("\n".join(keep[:40]))
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
