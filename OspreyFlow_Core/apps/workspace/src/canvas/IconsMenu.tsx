// The Icons control (ADR-079): the analyst chooses, for each type of node now in view, the icon drawn
// inside its shape: the ontology's default, another of the built-in drawings, none, or a small
// picture of their own. The choice is kept in this browser only, and a picture is cut to a thumbnail
// here and never sent anywhere, so it is a way of looking, not a change to the case.
import { useEffect, useId, useRef, useState } from "react";

import type { EntityTypeDef } from "../../../../packages/schemas/generated";
import { GLYPH_NAMES } from "../color/nodeGlyphs";
import { getIconChoices, onIconChoicesChange, setIconChoice } from "./iconChoices";
import { PICTURE_ACCEPT, thumbnailFromFile } from "./iconImage";

export interface IconsMenuProps {
  /** The ontology's entity types, which say each type's default icon. */
  entityTypes: readonly EntityTypeDef[];
  /** The names of the types that have a node in view now; a type not in view is not offered. */
  getTypesInView: () => readonly string[];
  /** Turns a file into the thumbnail kept for a type. Replaced in tests; the browser's own otherwise. */
  makeThumbnail?: (file: File) => Promise<string>;
}

const DEFAULT_VALUE = "";
const NONE_VALUE = "none";
const IMAGE_VALUE = "image";

export function IconsMenu({ entityTypes, getTypesInView, makeThumbnail = thumbnailFromFile }: IconsMenuProps) {
  const [open, setOpen] = useState(false);
  const [, bump] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => onIconChoicesChange(() => bump((n) => n + 1)), []);

  const choices = getIconChoices();
  const typesInView = open ? getTypesInView() : [];
  const inView = new Set(typesInView);
  const types = entityTypes
    .filter((type) => inView.has(type.name))
    .sort((a, b) => a.name.localeCompare(b.name, "en-GB"));

  function choose(type: string, value: string): void {
    setNotice(null);
    if (value === IMAGE_VALUE) return; // already the choice; nothing to change
    if (value === DEFAULT_VALUE) setIconChoice(type, null);
    else if (value === NONE_VALUE) setIconChoice(type, { kind: "none" });
    else if (value.startsWith("glyph:")) setIconChoice(type, { kind: "glyph", name: value.slice("glyph:".length) });
  }

  async function takePicture(type: string, file: File | undefined): Promise<void> {
    if (file === undefined) return;
    setNotice(null);
    try {
      const dataUrl = await makeThumbnail(file);
      const kept = setIconChoice(type, { kind: "image", dataUrl });
      if (!kept) setNotice("This browser would not keep the picture, so it holds for this page only.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "That file could not be used.");
    }
  }

  return (
    <div
      // A segment of the canvas toolbar's Show group, its panel laid over the canvas below it.
      className="canvas-menu"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          button.current?.focus();
        }
      }}
    >
      <button
        ref={button}
        type="button"
        className="radial-menu__item"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title="Choose the icon drawn inside each type of node"
        onClick={() => setOpen((v) => !v)}
      >
        Icons
      </button>
      {open && (
        <div
          id={panelId}
          className="canvas-menu-panel"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-4)",
            padding: "var(--sp-8)",
            width: 340,
            background: "var(--surface-raised)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          {types.length === 0 ? <span>No nodes in view to give an icon.</span> : null}
          {types.map((type) => {
            const chosen = choices[type.name];
            const value =
              chosen === undefined
                ? DEFAULT_VALUE
                : chosen.kind === "glyph"
                  ? `glyph:${chosen.name}`
                  : chosen.kind === "image"
                    ? IMAGE_VALUE
                    : NONE_VALUE;
            return (
              <div key={type.name} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ minWidth: "8ch" }}>{type.name}</span>
                {chosen?.kind === "image" ? (
                  <img
                    src={chosen.dataUrl}
                    alt={`Your picture for ${type.name}`}
                    width={24}
                    height={24}
                    style={{ borderRadius: 4 }}
                  />
                ) : null}
                <select
                  aria-label={`Icon for ${type.name}`}
                  value={value}
                  onChange={(event) => choose(type.name, event.target.value)}
                >
                  <option value={DEFAULT_VALUE}>{`Default (${type.icon ?? "none"})`}</option>
                  {GLYPH_NAMES.map((name) => (
                    <option key={name} value={`glyph:${name}`}>
                      {name}
                    </option>
                  ))}
                  <option value={NONE_VALUE}>None</option>
                  {chosen?.kind === "image" ? <option value={IMAGE_VALUE}>Your picture</option> : null}
                </select>
                {type.icon_by_value ? (
                  <span style={{ color: "var(--text-secondary)", flexBasis: "100%" }}>
                    {`Choosing an icon here replaces the icons chosen by ${type.icon_by_value.property.replaceAll("_", " ")}.`}
                  </span>
                ) : null}
                <input
                  type="file"
                  accept={PICTURE_ACCEPT}
                  aria-label={`Picture for ${type.name}`}
                  style={{ maxWidth: "100%" }}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = ""; // so choosing the same file again is heard
                    void takePicture(type.name, file);
                  }}
                />
              </div>
            );
          })}
          {notice !== null ? <span role="status">{notice}</span> : null}
          <span style={{ color: "var(--text-secondary)" }}>
            Kept in this browser only; it does not change the case. A picture is cut to a small square
            here and not sent anywhere.
          </span>
        </div>
      )}
    </div>
  );
}
