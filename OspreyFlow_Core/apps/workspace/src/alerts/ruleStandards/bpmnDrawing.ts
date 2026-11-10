// What *Show as BPMN* draws (`06_DECISIONS.md` ADR-146 decision 3): the three elements of a rule's
// stored BPMN 2.0 process, read from the `.bpmn` the Conduit exports
// (`packages/rule_standards/codec.py`), never from the form. A file that is not one process of
// one start event, one business-rule task and one end event, joined in that order, is not drawn:
// the drawing says so instead of guessing.

export const BPMN_MODEL = "http://www.omg.org/spec/BPMN/20100524/MODEL";

export interface BpmnElement {
  id: string;
  /** The element's name as the file gives it ("As data loads, after commit"). */
  name: string;
}

export interface BpmnDrawing {
  /** The process's name: the rule's. */
  rule: string;
  start: BpmnElement;
  task: BpmnElement;
  end: BpmnElement;
}

function only(process: Element, tag: string): Element | null {
  const found = process.getElementsByTagNameNS(BPMN_MODEL, tag);
  return found.length === 1 ? found[0]! : null;
}

function element(found: Element): BpmnElement {
  return {
    id: found.getAttribute("id") ?? "",
    name: found.getAttribute("name") ?? "",
  };
}

/** The drawing, or `null` for a file that is not a rule's three elements in order. */
export function readBpmnDrawing(xml: string): BpmnDrawing | null {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.getElementsByTagName("parsererror").length > 0) return null;
  const processes = doc.getElementsByTagNameNS(BPMN_MODEL, "process");
  if (processes.length !== 1) return null;
  const process = processes[0]!;
  const start = only(process, "startEvent");
  const task = only(process, "businessRuleTask");
  const end = only(process, "endEvent");
  if (start === null || task === null || end === null) return null;
  const [s, t, e] = [element(start), element(task), element(end)];
  const flows = new Set(
    Array.from(process.getElementsByTagNameNS(BPMN_MODEL, "sequenceFlow")).map(
      (flow) =>
        `${flow.getAttribute("sourceRef")}>${flow.getAttribute("targetRef")}`,
    ),
  );
  if (
    flows.size !== 2 ||
    !flows.has(`${s.id}>${t.id}`) ||
    !flows.has(`${t.id}>${e.id}`)
  )
    return null;
  return {
    rule: process.getAttribute("name") ?? "",
    start: s,
    task: t,
    end: e,
  };
}

/** The drawing in words, for the picture's accessible name. */
export function drawingWords(drawing: BpmnDrawing): string {
  return (
    `A BPMN process of three elements: a start event, “${drawing.start.name}”, then a ` +
    `business-rule task, “${drawing.task.name}”, then an end event, “${drawing.end.name}”.`
  );
}
