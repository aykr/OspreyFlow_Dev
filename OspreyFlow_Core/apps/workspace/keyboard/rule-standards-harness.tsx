// L2.11a's keyboard and axe harness (`06_DECISIONS.md` ADR-146 decision 3): *Show as BPMN* beside a
// rule's name, as the rule editor mounts it, drawing the `.bpmn` the codec really writes
// (`src/alerts/ruleStandards/fixtures/`, kept equal to `to_bpmn`'s output by
// `tests/rule_standards/test_codec.py`). Nothing here reaches a server; the data is synthetic (rule 9).
//
// States: none (the button); `open=1` (the drawing open); `file=other` (a stored file that is not a
// rule's process, so nothing is drawn). `keyboard/rule-standards.spec.ts` walks it by keyboard.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import BPMN from "../src/alerts/ruleStandards/fixtures/visits-to-listed-people.bpmn?raw";
import { ShowAsBpmn } from "../src/alerts/ruleStandards/ShowAsBpmn";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const params = new URLSearchParams(window.location.search);
const xml =
  params.get("file") === "other"
    ? BPMN.replace(
        "</bpmn:endEvent>",
        '</bpmn:endEvent><bpmn:endEvent id="then_2" name="Another end"/>',
      )
    : BPMN;

function Harness() {
  return (
    <main
      style={{
        padding: "var(--sp-16)",
        background: "var(--surface-app)",
        color: "var(--text-primary)",
        minHeight: "100vh",
      }}
    >
      <h1 style={{ fontSize: "var(--fs-19)", margin: "0 0 var(--sp-12)" }}>
        Visits to listed people
      </h1>
      <p style={{ color: "var(--text-secondary)" }}>
        A rule on Prison visits (synthetic), live.
      </p>
      <ShowAsBpmn bpmnXml={xml} />
      <button
        type="button"
        className="btn"
        style={{ marginLeft: "var(--sp-8)" }}
      >
        Export
      </button>
      <p id="editor-heard" role="status" style={{ color: "var(--text-secondary)" }}>
        The editor heard Escape 0 time(s).
      </p>
    </main>
  );
}

// The editor's own Escape, as the rule editor around the button has one: the keyboard spec reads
// what it heard, to prove the drawing keeps Escape while open and gives it back when closed.
let heard = 0;
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  heard += 1;
  const said = document.getElementById("editor-heard");
  if (said) said.textContent = `The editor heard Escape ${heard} time(s).`;
});

createRoot(document.getElementById("root")!).render(<Harness />);
// `open=1`: the drawing open before the axe scan reads the page. React renders after this script
// returns, so the button is waited for frame by frame; one frame was not always enough, and the
// scan then read the page with the drawing shut (found by planting a nameless Close: only one look
// of three went red).
function openWhenDrawn(): void {
  const button = document.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]');
  if (button) button.click();
  else requestAnimationFrame(openWhenDrawn);
}
if (params.get("open") === "1") openWhenDrawn();
