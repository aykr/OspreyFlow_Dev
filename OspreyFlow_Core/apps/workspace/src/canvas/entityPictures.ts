// The browser's half of an entity's own picture (ADR-105): the thumbnail step, which draws on a canvas
// (`thumbnailFromFile`), bound into the shared package's store and client (ADR-152 R2, PL4 slice D3e). Every name
// the workspace used from here is passed on from the package, so no importer changed; a page that is not the
// workspace binds its own thumbnail step.
import { bindEntityThumbnail } from "@ospreyflow/glass-shared";

import { thumbnailFromFile } from "./iconImage";

bindEntityThumbnail(thumbnailFromFile);

export {
  entityPictureFor,
  forgetEntityPictures,
  loadEntityPictures,
  onEntityPicturesChange,
  removeEntityPicture,
  setEntityPicture,
  setEntityPictureForTest,
  type PictureApi,
} from "@ospreyflow/glass-shared";
