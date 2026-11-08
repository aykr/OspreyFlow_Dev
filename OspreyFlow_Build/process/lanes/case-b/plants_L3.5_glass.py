"""L3.5's red record for the Glass (rule 15), reproducible: each plant breaks one rule of the Model
tab's proposals block where its Vitest or keyboard case reaches it, runs that case, and puts the
file back. Run from `OspreyFlow_Core/apps/workspace` with port 5185 free:

    python3 ../../../OspreyFlow_Build/process/lanes/case-b/plants_L3.5_glass.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

MP = "src/linktypes/ModelProposals.tsx"
PT = "src/linktypes/ProposedTypes.tsx"
HTTP = "src/linktypes/http.ts"
VT = "src/linktypes/ModelProposals.test.tsx"
PVT = "src/linktypes/ProposedTypes.test.tsx"
KB = "keyboard/model-proposals.spec.ts"

PLANTS = [
    ("what a type means not shown", MP, "`What it means: “${p.reason}”`", "`${p.name}`",
     ["vitest", VT, "lists the dataset's proposals"]),
    ("acceptance sent without its basis", MP,
     '    if (deciding.decision === "accept" && basis === "") {', "    if (false) {",
     ["vitest", VT, "adds a type to the draft model"]),
    ("a refusal in our words, not the Conduit's", MP,
     '    if (error.kind === "refused") return error.message;', "",
     ["vitest", VT, "declines with a reason"]),
    ("a 403 or 404 not hiding the block", MP,
     'error.kind === "forbidden" || error.kind === "not_found")) setHidden(true);', "false)) setHidden(true);",
     ["vitest", VT, "is not drawn at all"]),
    ("a failed read shown as none", MP, "      else setLoadFailed(true);", "      else setProposals([]);",
     ["vitest", VT, "says when the list could not be read"]),
    ("the model's refusal in generic words", HTTP, '  if (body.error === "model_refused") {', "  if (false) {",
     ["vitest", VT, "offers an accepted type lost from the model"]),
    ("an accepted type lost from the model not decidable", MP,
     '  return p.status === "pending" || (p.status === "accepted" && !p.in_model);', '  return p.status === "pending";',
     ["vitest", VT, "offers an accepted type lost from the model"]),
    ("a live type tagged as in the draft", MP,
     '    if (p.in_model === "live") return { words: "In the live model", tag: "govuk-tag--green" };', "",
     ["vitest", VT, "tags an accepted type live"]),
    ("Admin offers Promote for a dataset's proposal", PT,
     '            {p.status === "pending" && !p.dataset_id && (', '            {p.status === "pending" && (',
     ["vitest", PVT, "offers no Promote or Reject"]),
    ("Escape gives focus to nothing", MP, "    setRefocus(openedBy.current);", "    setRefocus(null);",
     ["playwright", KB, "Escape closes the decision form"]),
    ("the outcome not focused after a decision", MP, "    if (done) outcome.current?.focus();", "",
     ["playwright", KB, "added to the draft model by keyboard"]),
]

held = 0
for title, file, old, new, (runner, spec, name) in PLANTS:
    path = pathlib.Path(file)
    before = path.read_text()
    assert before.count(old) == 1, f"{title}: the plant's text is not found once in {file}"
    path.write_text(before.replace(old, new))
    try:
        if runner == "vitest":
            cmd = ["npx", "vitest", "run", spec, "-t", name]
        else:
            cmd = ["npx", "playwright", "test", "-c", "keyboard/playwright.config.ts", spec, "-g", name]
        done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    finally:
        path.write_text(before)
    red = done.returncode != 0
    held += 0 if red else 1
    print(f"| {title} | `{file}` | {spec} › {name} | {'red' if red else 'STILL GREEN'} |")
sys.exit(1 if held else 0)
