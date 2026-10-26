// @vitest-environment jsdom
// ADR-094 step 1: in Map, a link with a time can name the column holding its text, so each row's
// message or document becomes readable and extractable.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema, RecipeEdge, RecipeEntity } from "../../../../../packages/schemas/generated";
import { ElementInspector } from "./ElementInspector";

afterEach(cleanup);

const ONTOLOGY = {
  version: 11,
  entity_types: [
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "circle", properties: [] },
    { name: "Document", pole_class: "object", channel: "violet", shape: "page", properties: [] },
  ],
  edge_types: [
    { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"], temporal: true, basis: "direct" },
    { name: "OWNS", from: ["Endpoint"], to: ["Endpoint"], basis: "direct" },
  ],
} as unknown as OntologySchema;

function mount(edge: RecipeEdge, onChangeEdge = vi.fn(), transforms: unknown[] = []) {
  render(
    <ElementInspector
      selection={{ kind: "edge", edge, index: 0, fromType: "Endpoint", toType: "Endpoint" } as never}
      ontology={ONTOLOGY}
      transforms={transforms as never}
      sourceFieldNames={["sender", "recipient", "sent_at", "text"]}
      baselineClassification="OFFICIAL"
      classificationOrder={["OFFICIAL"]}
      onChangeEntity={vi.fn()}
      onChangeEdge={onChangeEdge}
      onDelete={vi.fn()}
      onPreviewHandling={vi.fn()}
    />,
  );
  return onChangeEdge;
}

describe("ElementInspector: a link's text", () => {
  it("marks a column as the link's message text", () => {
    const onChangeEdge = mount({ type: "COMMUNICATED_WITH", from: "a", to: "b", temporal: { at: { field: "sent_at" } } });
    fireEvent.change(screen.getByLabelText("Text the model can read"), { target: { value: "message_text" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(
      expect.objectContaining({ content: { kind: "message_text", field: "sender" } }),
    );
  });

  it("changes the column and can clear it", () => {
    const edge: RecipeEdge = {
      type: "COMMUNICATED_WITH",
      from: "a",
      to: "b",
      temporal: { at: { field: "sent_at" } },
      content: { kind: "message_text", field: "sender" },
    };
    const onChangeEdge = mount(edge);
    fireEvent.change(screen.getByLabelText("Column holding the text"), { target: { value: "text" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(expect.objectContaining({ content: { kind: "message_text", field: "text" } }));
    fireEvent.change(screen.getByLabelText("Text the model can read"), { target: { value: "" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(expect.objectContaining({ content: null }));
  });

  it("is not offered on a link with no time, which has no events to carry text", () => {
    mount({ type: "OWNS", from: "a", to: "b" });
    expect(screen.queryByLabelText("Text the model can read")).toBeNull();
  });
});

describe("ElementInspector: content an entity holds (ADR-094 step 2)", () => {
  function mountEntity(onChangeEntity = vi.fn()) {
    render(
      <ElementInspector
        selection={
          {
            kind: "entity",
            entity: { ref: "phone", pole_class: "object", type: "Endpoint", properties: {} },
          } as never
        }
        ontology={ONTOLOGY}
        transforms={[]}
        sourceFieldNames={["phone", "photo_path"]}
        baselineClassification="OFFICIAL"
        classificationOrder={["OFFICIAL"]}
        onChangeEntity={onChangeEntity}
        onChangeEdge={vi.fn()}
        onDelete={vi.fn()}
        onPreviewHandling={vi.fn()}
      />,
    );
    return onChangeEntity;
  }

  it("marks a column as an image file the entity holds, and says where the path is from", () => {
    const onChangeEntity = mountEntity();
    fireEvent.change(screen.getByLabelText("Content this holds"), { target: { value: "image_file" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(
      expect.objectContaining({ content: { kind: "image_file", field: "phone" } }),
    );
    expect(screen.getByText(/relative to the export's own folder/)).toBeTruthy();
  });
});

// ADR-127 decision 1 and its amendment: a Document holds only its own text. An image or a video on a
// Document entity is refused at Map save, so the inspector does not offer it there.
describe("ElementInspector: a Document's own text (ADR-127)", () => {
  function mountDocument(content: RecipeEntity["content"] = null, onChangeEntity = vi.fn()) {
    render(
      <ElementInspector
        selection={
          {
            kind: "entity",
            entity: { ref: "doc", pole_class: "object", type: "Document", properties: {}, content },
          } as never
        }
        ontology={ONTOLOGY}
        transforms={[]}
        sourceFieldNames={["report_text", "title"]}
        baselineClassification="OFFICIAL"
        classificationOrder={["OFFICIAL"]}
        onChangeEntity={onChangeEntity}
        onChangeEdge={vi.fn()}
        onDelete={vi.fn()}
        onPreviewHandling={vi.fn()}
      />,
    );
    return onChangeEntity;
  }

  it("offers only the Document's own text, labelled for what it is", () => {
    mountDocument();
    expect(screen.queryByLabelText("Content this holds")).toBeNull();
    const select = screen.getByLabelText("Its own text") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["", "document_text"]);
    expect(screen.queryByText("Image file")).toBeNull();
    expect(screen.queryByText("Video file")).toBeNull();
    expect(screen.queryByText(/relative to the export's own folder/)).toBeNull();
  });

  it("marks a column as its own text, and names which column holds it", () => {
    const onChangeEntity = mountDocument();
    fireEvent.change(screen.getByLabelText("Its own text"), { target: { value: "document_text" } });
    expect(onChangeEntity).toHaveBeenLastCalledWith(
      expect.objectContaining({ content: { kind: "document_text", field: "report_text" } }),
    );
    cleanup();
    const again = mountDocument({ kind: "document_text", field: "report_text" });
    fireEvent.change(screen.getByLabelText("Column holding its text"), { target: { value: "title" } });
    expect(again).toHaveBeenLastCalledWith(
      expect.objectContaining({ content: { kind: "document_text", field: "title" } }),
    );
  });

  it("keeps the holder wording, with the files, for every other entity type", () => {
    render(
      <ElementInspector
        selection={
          {
            kind: "entity",
            entity: { ref: "phone", pole_class: "object", type: "Endpoint", properties: {} },
          } as never
        }
        ontology={ONTOLOGY}
        transforms={[]}
        sourceFieldNames={["phone"]}
        baselineClassification="OFFICIAL"
        classificationOrder={["OFFICIAL"]}
        onChangeEntity={vi.fn()}
        onChangeEdge={vi.fn()}
        onDelete={vi.fn()}
        onPreviewHandling={vi.fn()}
      />,
    );
    const select = screen.getByLabelText("Content this holds") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      "",
      "document_text",
      "image_file",
      "video_file",
    ]);
    expect(screen.queryByLabelText("Its own text")).toBeNull();
  });
});

describe("ElementInspector: when a link occurred (found building the AML deck, 11 October 2026)", () => {
  it("says a link with no time is not recorded, rather than showing a column it will not use", () => {
    mount({ type: "COMMUNICATED_WITH", from: "a", to: "b" });
    expect((screen.getByLabelText("When it occurred") as HTMLSelectElement).value).toBe("");
    expect(screen.queryByText("sender")).toBeNull();
    expect(screen.queryByLabelText("Text the model can read")).toBeNull();
  });

  it("records the time from a column when asked, and clears it again", () => {
    const onChangeEdge = mount({ type: "COMMUNICATED_WITH", from: "a", to: "b" });
    fireEvent.change(screen.getByLabelText("When it occurred"), { target: { value: "column" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(expect.objectContaining({ temporal: { at: { field: "sender" } } }));
    cleanup();
    const again = mount({ type: "COMMUNICATED_WITH", from: "a", to: "b", temporal: { at: { field: "sent_at" } } });
    fireEvent.change(screen.getByLabelText("When it occurred"), { target: { value: "" } });
    expect(again).toHaveBeenLastCalledWith(expect.objectContaining({ temporal: null, content: null }));
  });
});


// --- ADR-127 decision 11: a link's span ----------------------------------------------------------

const TIMED: RecipeEdge = {
  type: "COMMUNICATED_WITH",
  from: "a",
  to: "b",
  temporal: { at: { field: "sent_at", transform: "datetime" } },
};
const DATETIME = [{ name: "datetime", arity: 1 }];

describe("ElementInspector: when a link ended", () => {
  it("offers an end only to a link that has a time, and starts with none recorded", () => {
    mount({ type: "COMMUNICATED_WITH", from: "a", to: "b" });
    expect(screen.queryByLabelText("When it ended")).toBeNull();
    cleanup();
    mount(TIMED);
    expect((screen.getByLabelText("When it ended") as HTMLSelectElement).value).toBe("");
  });

  it("binds the end to a column, with the datetime transform when the catalogue has it", () => {
    const onChangeEdge = mount(TIMED, vi.fn(), DATETIME);
    fireEvent.change(screen.getByLabelText("When it ended"), { target: { value: "column" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(
      expect.objectContaining({
        temporal: {
          at: { field: "sent_at", transform: "datetime" },
          valid_to: { field: "sender", transform: "datetime" },
        },
      }),
    );
  });

  it("changes the end's column and its transform, and says an empty cell means still open", () => {
    const edge: RecipeEdge = {
      ...TIMED,
      temporal: { at: { field: "sent_at", transform: "datetime" }, valid_to: { field: "sender", transform: "datetime" } },
    };
    const onChangeEdge = mount(edge, vi.fn(), DATETIME);
    expect(screen.getByText(/an empty cell means it is still going/i)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Column holding when it ended"), { target: { value: "recipient" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(
      expect.objectContaining({
        temporal: {
          at: { field: "sent_at", transform: "datetime" },
          valid_to: { field: "recipient", transform: "datetime" },
        },
      }),
    );
    // The inspector is controlled by the edge it is given, so each change is read against it.
    fireEvent.change(screen.getByLabelText("Transform for when it ended"), { target: { value: "" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(
      expect.objectContaining({
        temporal: { at: { field: "sent_at", transform: "datetime" }, valid_to: { field: "sender" } },
      }),
    );
  });

  it("clears the end back to one moment", () => {
    const edge: RecipeEdge = { ...TIMED, temporal: { at: { field: "sent_at" }, valid_to: { field: "sender" } } };
    const onChangeEdge = mount(edge, vi.fn(), DATETIME);
    fireEvent.change(screen.getByLabelText("When it ended"), { target: { value: "" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(expect.objectContaining({ temporal: { at: { field: "sent_at" } } }));
  });

  it("keeps the end when the start's binding is edited", () => {
    const edge: RecipeEdge = { ...TIMED, temporal: { at: { field: "sent_at" }, valid_to: { field: "sender" } } };
    const onChangeEdge = mount(edge, vi.fn(), DATETIME);
    // The start's own editor is the first binding editor on the link; change its transform.
    const [startTransform] = screen.getAllByRole("combobox").filter(
      (el) => Array.from((el as HTMLSelectElement).options).some((o) => o.text === "No transform") && el.getAttribute("aria-label") === null,
    );
    fireEvent.change(startTransform!, { target: { value: "datetime" } });
    expect(onChangeEdge).toHaveBeenLastCalledWith(
      expect.objectContaining({
        temporal: { at: { field: "sent_at", transform: "datetime" }, valid_to: { field: "sender" } },
      }),
    );
  });
});
