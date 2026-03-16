import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));

function readSourceFile(relativePathFromTestDir: string): string {
  return readFileSync(path.resolve(TEST_DIR, relativePathFromTestDir), "utf8");
}

test("layout catalog sorting avoids host-default localeCompare in hydration path", () => {
  const source = readSourceFile("../../app/dev/layout-catalog/LayoutCatalogClient.tsx");

  assert.match(source, /compareLayoutNames\(/);
  assert.doesNotMatch(source, /\.localeCompare\(/);
});

test("session sorting uses timestamp comparator instead of localeCompare", () => {
  const storeSource = readSourceFile("../store.ts");
  const dialogSource = readSourceFile("../../components/home/SessionListDialog.tsx");

  assert.match(storeSource, /compareUpdatedAt/);
  assert.doesNotMatch(storeSource, /\.localeCompare\(/);

  assert.match(dialogSource, /compareUpdatedAt/);
  assert.doesNotMatch(dialogSource, /\.localeCompare\(/);
});
