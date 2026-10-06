// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { placeOf, selectionIn } from "./designation";

// ADR-098 decision 5: words marked as an entity are sent with where they are in the text, which the
// server checks against the text it showed.
describe("selectionIn", () => {
  it("gives the selected words and their place in the container's text, across runs, trimmed", () => {
    const p = document.createElement("p");
    p.innerHTML = "<span>Dana </span><button>MERCER</button><span> wrote to Callum</span>";
    document.body.append(p);
    const range = document.createRange();
    range.setStart(p.childNodes[0]!.firstChild!, 0);
    range.setEnd(p.childNodes[1]!.firstChild!, 6);
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
    expect(selectionIn(p)).toEqual({ text: "Dana MERCER", start: 0, end: 11 });

    const loose = document.createRange();
    loose.setStart(p.childNodes[2]!.firstChild!, 0); // " wrote"
    loose.setEnd(p.childNodes[2]!.firstChild!, 6);
    selection.removeAllRanges();
    selection.addRange(loose);
    expect(selectionIn(p)).toEqual({ text: "wrote", start: 12, end: 17 });
  });

  it("is null for nothing selected or a selection outside the container", () => {
    const p = document.createElement("p");
    p.textContent = "Dana";
    const elsewhere = document.createElement("div");
    elsewhere.textContent = "other";
    document.body.append(p, elsewhere);
    window.getSelection()!.removeAllRanges();
    expect(selectionIn(p)).toBeNull();
    const range = document.createRange();
    range.selectNodeContents(elsewhere);
    window.getSelection()!.addRange(range);
    expect(selectionIn(p)).toBeNull();
  });
});

describe("placeOf", () => {
  const text = "Dana MERCER wrote to Callum PRICE about MERCER's plant.";

  it("keeps a selected place when the words are still the same there", () => {
    expect(placeOf(text, "MERCER", { text: "MERCER", start: 40, end: 46 })).toEqual({ start: 40, end: 46 });
  });

  it("finds the first place of typed words, and none for words not in the text", () => {
    expect(placeOf(text, "Callum PRICE", null)).toEqual({ start: 21, end: 33 });
    expect(placeOf(text, "  MERCER ", null)).toEqual({ start: 5, end: 11 });
    expect(placeOf(text, "Ken Lay", null)).toBeNull();
  });
});
