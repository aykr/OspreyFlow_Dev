// Words in a document marked as an entity by the analyst (ADR-098 decision 5): what was selected,
// and where it is in the document's text, which the server checks against the text it showed.

export interface SelectedWords {
  text: string;
  start: number;
  end: number;
}

/** The words selected inside `container`, trimmed, with their character place in its text; `null`
 * when nothing is selected there. */
export function selectionIn(container: HTMLElement): SelectedWords | null {
  const selection = container.ownerDocument.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null;
  const before = container.ownerDocument.createRange();
  before.selectNodeContents(container);
  before.setEnd(range.startContainer, range.startOffset);
  const raw = range.toString();
  const lead = raw.length - raw.trimStart().length;
  const text = raw.trim();
  if (text === "") return null;
  const start = before.toString().length + lead;
  return { text, start, end: start + text.length };
}

/** Where `words` are in `text`: the selected place if the words there are still these, else their
 * first place; `null` when they are not in the text. */
export function placeOf(
  text: string,
  words: string,
  selected: SelectedWords | null,
): { start: number; end: number } | null {
  const wanted = words.trim();
  if (wanted === "") return null;
  if (selected && selected.text === wanted && text.slice(selected.start, selected.end) === wanted) {
    return { start: selected.start, end: selected.end };
  }
  const start = text.indexOf(wanted);
  return start < 0 ? null : { start, end: start + wanted.length };
}
