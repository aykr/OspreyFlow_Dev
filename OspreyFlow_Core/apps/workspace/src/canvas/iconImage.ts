// Turning a file the analyst chose into the small picture kept for a type (ADR-079). The file is read
// and cut in this browser and never sent anywhere.
import { MAX_IMAGE_ICON_CHARS, isSafeImageDataUrl } from "../color/nodeVisual";

export const MAX_PICTURE_BYTES = 5 * 1024 * 1024;
export const PICTURE_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";
const TYPES = new Set(PICTURE_ACCEPT.split(","));
const THUMBNAIL_SIDES = [64, 48, 32];

/** Why a file cannot be taken as a picture, or `null` when it can. An SVG is refused on purpose: it
 * can carry scripts and links, and only a raster is ever drawn into a node. */
export function checkPictureFile(file: { type: string; size: number }): string | null {
  if (!TYPES.has(file.type)) return "That file is not a picture I can use: png, jpeg, webp or gif.";
  if (file.size <= 0) return "That file is empty.";
  if (file.size > MAX_PICTURE_BYTES) return "That picture is too large: 5 MB at most.";
  return null;
}

/** The middle square of a `width` by `height` picture. */
export function squareCrop(width: number, height: number): { sx: number; sy: number; side: number } {
  const side = Math.max(1, Math.min(width, height));
  return { sx: Math.floor((width - side) / 2), sy: Math.floor((height - side) / 2), side };
}

function load(file: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("That file could not be read as a picture."));
    };
    image.src = url;
  });
}

/** The middle square of the file, drawn at 64 units (smaller if it would still be too big to keep) as
 * a PNG data address. Rejects with a sentence for the analyst when the file cannot be used. */
export async function thumbnailFromFile(file: File): Promise<string> {
  const refusal = checkPictureFile(file);
  if (refusal !== null) throw new Error(refusal);
  const image = await load(file);
  const { sx, sy, side } = squareCrop(image.naturalWidth, image.naturalHeight);
  for (const size of THUMBNAIL_SIDES) {
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    if (context === null) throw new Error("This browser cannot make a thumbnail.");
    context.drawImage(image, sx, sy, side, side, 0, 0, size, size);
    const url = canvas.toDataURL("image/png");
    if (isSafeImageDataUrl(url) && url.length <= MAX_IMAGE_ICON_CHARS) return url;
  }
  throw new Error("That picture is too detailed to keep small; try a simpler one.");
}
