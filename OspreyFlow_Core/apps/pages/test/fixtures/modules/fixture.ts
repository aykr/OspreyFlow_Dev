// A throw-away module for the foundation's own tests: it uses syntax newer than ES2018 (to show the build lowers it)
// and imports from the shared package (to show the build resolves that package's source). Not part of the product.
import { PRODUCT_STATEMENT } from "@ospreyflow/glass-shared";

interface PageData {
  rows?: number;
}

const raw = document.getElementById("page-data")?.textContent ?? "{}";
const data = JSON.parse(raw) as PageData;
const count = data.rows ?? 0;
document.title = `${count} rows: ${PRODUCT_STATEMENT.slice(0, 12)}`;
