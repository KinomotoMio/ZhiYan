import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(path.resolve(TEST_DIR, relativePath), "utf8");
}

test("editor workspace renders centi-deck sidebar thumbnails from the loaded artifact", () => {
  const source = readSource("../EditorWorkspace.tsx");

  assert.match(source, /mode="thumbnail"/);
  assert.match(source, /artifactOverride=\{centiDeckArtifact\}/);
  assert.match(source, /缩略图加载中/);
});

test("session editor page treats centi-deck artifact as a ready result", () => {
  const source = readSource("../../../app/sessions/[sessionId]/editor/page.tsx");

  assert.match(source, /presentationSlidevMarkdown \|\| centiDeckArtifact \|\| latestJob\?\.job_id/);
});
