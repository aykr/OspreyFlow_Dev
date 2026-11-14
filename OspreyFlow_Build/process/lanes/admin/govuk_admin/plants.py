"""The GOV.UK Admin pass's plants (ADR-145 Amendment 16, rule 15): each check in keyboard/admin-look.spec.ts, and
the coming-section keyboard case, planted alone in the shape main drew or a regression would take, run, and the
tree restored from git. A plant that stays green is a check that cannot fail for its reason.

Run from the repository root, with OSPREY_PORTS_SLOT set: python OspreyFlow_Build/process/lanes/admin/govuk_admin/plants.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WS = ROOT / "OspreyFlow_Core/apps/workspace"
PEOPLE = "src/admin/sections/People.tsx"
PLACE = "src/admin/AdminPlace.tsx"
CSS = "src/admin/admin.css"
LOOK = "keyboard/admin-look.spec.ts"

# name, [(file, old, new)], spec files, -g filter, the assertion it must fail (a regex over the source line
# Playwright points at): a plant is red only when every failure points at that assertion, so a harness break or
# another check failing first counts as missed (rule 15: a fallthrough proves nothing).
PLANTS = [
    ("name in mono, as main drew it", [(PEOPLE, 'className="admin-person__name" data-person-name', 'className="value" data-person-name')],
     [LOOK], "one h1", r"m\.nameFont"),
    ("Super user drawn as a button, as main drew it", [(PEOPLE, 'className="admin-row-actions__link"\n                aria-label={`Super user preset', 'className="btn"\n                aria-label={`Super user preset')],
     [LOOK], "one h1", r"a\) => a\.button\)"),
    ("Save drawn as a link", [(PEOPLE, 'className="admin-row-actions__primary"', 'className="admin-row-actions__link"')],
     [LOOK], "one h1", r"a\) => a\.button\)"),
    ("headers allowed to wrap at desktop width", [(CSS, "@media (min-width: 1020px) { .admin-place__section th { white-space: nowrap; } }", "")],
     [LOOK], "one h1", r"m\.headerLines"),
    # Not "main's long header back": with headers kept to one line that is harmless (tried: green), so the
    # height check gets its own plant, headers on one line but padded as tall as main's wrapped ones.
    ("headers on one line but as tall as main's", [(CSS, "@media (min-width: 1020px) { .admin-place__section th { white-space: nowrap; } }",
                                                   "@media (min-width: 1020px) { .admin-place__section th { white-space: nowrap; padding-block: var(--sp-40); } }")],
     [LOOK], "one h1", r"m\.headerHeight"),
    ("People's parts back to h4, as main had them", [(PEOPLE, '<h2 className="value" style={{ margin: 0 }}>Invite a person</h2>', '<h4 className="value" style={{ margin: 0 }}>Invite a person</h4>')],
     [LOOK], "one h1", r"m\.headingLevels"),
    ("the h2s at the browser's size, above the h1", [(CSS, ".admin-place__section h2.value { font-size: var(--fs-13);", ".admin-place__section h2.value { font-size: 1.5em;")],
     [LOOK], "one h1", r"m\.h2sNotSmaller"),
    ("a coming item a button again, as main drew it", [(PLACE, '<span className="admin-nav__coming-item">', '<button type="button" className="admin-nav__coming-item">'),
                                                   (PLACE, '<span className="admin-nav__coming-what">{section.coming}</span>\n                    </span>', '<span className="admin-nav__coming-what">{section.coming}</span>\n                    </button>')],
     [LOOK, "keyboard/admin.spec.ts"], "one h1|coming section", r"m\.comingLinks|toBeFocused"),
    ("GOV.UK's 16px rule removed", [(CSS, '[data-brand="govuk"] .admin-place :is(.admin-nav__link', '[data-brand="none"] .admin-place :is(.admin-nav__link')],
     [LOOK], "Design System", r"m\.nav, m\.cell, m\.header, m\.rowLink, m\.comingWhat"),
    ("GOV.UK's 16px rule in every look", [(CSS, '[data-brand="govuk"] .admin-place :is(.admin-nav__link', '.admin-place :is(.admin-nav__link')],
     [LOOK], "keeps main", r"m\.nav, m\.cell, m\.header\]"),
    ("the row's links at GOV.UK's size in every look", [(CSS, "  font: inherit; color: var(--brass); background: none;", "  font: inherit; font-size: var(--fs-16); color: var(--brass); background: none;")],
     [LOOK], "Design System|keeps main", r"m\.rowLink"),
    ("a person's actions stacked one per line, as main's actions cell", [(CSS, ".admin-row-actions__line { display: flex; flex-wrap: wrap;", ".admin-row-actions__line { display: flex; flex-direction: column; align-items: flex-start; flex-wrap: wrap;"),
                                                                       (CSS, ".admin-row-actions__more { display: contents; }", ".admin-row-actions__more { display: flex; flex-direction: column; align-items: flex-start; }")],
     [LOOK], "Design System|keeps main", r"m\.row\)"),
]


def run(specs, grep):
    out = subprocess.run(
        ["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", *specs, "-g", grep, "--reporter=line"],
        cwd=WS, capture_output=True, text=True,
    ).stdout
    keep = [l for l in out.splitlines() if re.match(r"\s+\d+\) |\s+> \d+ \||\s+(Expected|Received)|\s+[-+] |\s+\d+ (passed|failed)", l)]
    return out, keep


def red_for_its_reason(out: str, why: str) -> tuple[bool, str]:
    failures = re.findall(r"^\s+\d+\) ", out, re.M)
    pointers = re.findall(r"^\s+> \d+ \|(.*)$", out, re.M)
    off = [p.strip() for p in pointers if not re.search(why, p)]
    if not failures:
        return False, "GREEN - the check misses it"
    if len(pointers) != len(failures) or off:
        return False, f"red for another reason ({len(failures)} failed, {len(pointers)} pointed, off: {off})"
    return True, f"RED at its assertion in {len(failures)} test(s)"


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
