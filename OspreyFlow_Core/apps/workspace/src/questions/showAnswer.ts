// *Show all on graph* under an Ask & Chat answer (v0.6.0 #5), as `App.tsx` and the keyboard harness both do it: the
// answer's items put on the canvas by id (`addByIds`, read on the server as this reader may see them), selected and
// brought into view; how many are not shown said, never which; past the working set's cap nothing added and the typed
// refusal said with its figures (rule 2). One function, so the harness proves the App's own steps.
import { addByIds, type ConnectionsContext } from "../connections/connectionsApi";
import type { WorkingSetDelta } from "../workingset/models";
import type { AnswerIds } from "./AnswerActions";

export interface ShowAnswerCanvas {
  applyDelta: (delta: WorkingSetDelta) => void;
  hasNode: (id: string) => boolean;
  /** Selects the ids on the canvas (the canvas's `highlightNodes`), and centres one. */
  highlightNodes: (nodeIds: readonly string[]) => void;
  centreOn: (nodeId: string) => void;
  /** Says something to the analyst (a notice). */
  say: (words: string) => void;
}

export async function showAnswerOnCanvas(context: ConnectionsContext, ids: AnswerIds, canvas: () => ShowAnswerCanvas | null): Promise<void> {
  try {
    const added = await addByIds(context, ids.nodeIds, ids.linkIds);
    const now = canvas();
    if (!now) return;
    if (added.kind === "limit_exceeded") {
      now.say(
        `Too many for the canvas: ${added.wouldBe.toLocaleString("en-GB")} ${added.capKind === "edges" ? "links" : "nodes"} against a limit of ${added.cap.toLocaleString("en-GB")}. Nothing was added; Save as a view, under the answer in Ask & Chat, keeps them all.`,
      );
      return;
    }
    for (const delta of added.deltas) now.applyDelta(delta);
    if (added.notShown > 0) now.say(`${added.notShown.toLocaleString("en-GB")} of this answer's items could not be shown.`);
    // Once drawn: every item of the answer on the canvas, selected together, the camera on the first.
    requestAnimationFrame(() => {
      const drawn = canvas();
      if (!drawn) return;
      drawn.highlightNodes(ids.nodeIds);
      const first = ids.nodeIds.find((id) => drawn.hasNode(id));
      if (first) drawn.centreOn(first);
    });
  } catch (error) {
    canvas()?.say(error instanceof Error ? error.message : String(error));
  }
}
