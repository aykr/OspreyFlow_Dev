// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { forgetEntityPictures, setEntityPictureForTest } from "./entityPictures";
import { forgetIconChoicesForTest, resolveIconForNode, setIconChoice, valueIconShownFor } from "./iconChoices";
import { valueIconFor } from "./valueIcons";

// ADR-128 Decision 4 (B7): the legend and the Inspector name a value icon only for a node that is
// drawn with it. `valueIconShownFor` is the one function both ask, and it must agree with the
// renderer (`resolveIconForNode`) in every case of the order of precedence.

const RULE = { property: "endpoint_kind", icons: { handle: "keypad" } } as const;
const PROPS = { endpoint_kind: "handle" };
const PHOTO = "data:image/png;base64,iVBORw0KGgo=";

beforeEach(() => {
  localStorage.clear();
  forgetIconChoicesForTest();
  forgetEntityPictures();
});
afterEach(() => {
  forgetIconChoicesForTest();
  forgetEntityPictures();
});

/** What the renderer actually draws for the node, as the name of a glyph, or its kind. */
function drawn(): string | null {
  const given = valueIconFor(RULE, PROPS);
  const icon = resolveIconForNode("n1", "Endpoint", "device", "#336699", given?.glyph);
  if (icon === null) return null;
  return icon.kind === "glyph" ? icon.name : icon.kind;
}

describe("the value icon named in the legend and the Inspector", () => {
  it("is named when nothing of the analyst's comes first, and the renderer draws it", () => {
    expect(valueIconShownFor("n1", "Endpoint", RULE, PROPS)).toEqual({ glyph: "keypad", value: "handle" });
    expect(drawn()).toBe("keypad");
  });

  it("is not named once the analyst has chosen a drawing for the type", () => {
    setIconChoice("Endpoint", { kind: "glyph", name: "shield" });
    expect(drawn()).toBe("shield");
    expect(valueIconShownFor("n1", "Endpoint", RULE, PROPS)).toBeNull();
  });

  it("is not named once the analyst has chosen no icon for the type", () => {
    setIconChoice("Endpoint", { kind: "none" });
    expect(drawn()).toBeNull();
    expect(valueIconShownFor("n1", "Endpoint", RULE, PROPS)).toBeNull();
  });

  it("is not named once the analyst has chosen a picture for the type", () => {
    setIconChoice("Endpoint", { kind: "image", dataUrl: PHOTO });
    expect(drawn()).toBe("image");
    expect(valueIconShownFor("n1", "Endpoint", RULE, PROPS)).toBeNull();
  });

  it("is not named for a node that has a picture of its own", () => {
    setEntityPictureForTest("n1", PHOTO);
    expect(drawn()).toBe("image");
    expect(valueIconShownFor("n1", "Endpoint", RULE, PROPS)).toBeNull();
    // Another node of the type, without a picture, still has it.
    expect(valueIconShownFor("n2", "Endpoint", RULE, PROPS)).toEqual({ glyph: "keypad", value: "handle" });
  });

  it("is named for nothing when the value maps nothing", () => {
    expect(valueIconShownFor("n1", "Endpoint", RULE, { endpoint_kind: "email" })).toBeNull();
    expect(valueIconShownFor("n1", "Endpoint", null, PROPS)).toBeNull();
  });
});
