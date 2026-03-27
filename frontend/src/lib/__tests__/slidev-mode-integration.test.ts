import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));

function readSourceFile(relativePathFromTestDir: string): string {
  return readFileSync(path.resolve(TEST_DIR, relativePathFromTestDir), "utf8");
}

test("planning panel and editor wire the slidev mode explicitly", () => {
  const planningSource = readSourceFile("../../components/create/PlanningPanel.tsx");
  const editorSource = readSourceFile("../../components/editor/EditorWorkspace.tsx");

  assert.match(planningSource, /onChangeGenerationMode\("slidev"\)/);
  assert.match(planningSource, /Slidev 模式/);
  assert.match(editorSource, /presentationOutputMode === "slidev"/);
  assert.match(editorSource, /<SlidevPreview/);
});

test("slidev preview uses hash routing and api exposes slidev persistence helpers", () => {
  const previewSource = readSourceFile("../../components/slides/SlidevPreview.tsx");
  const apiSource = readSourceFile("../api.ts");

  assert.match(previewSource, /url\.hash = `#\/\$\{safeSlide \+ 1\}`/);
  assert.doesNotMatch(previewSource, /searchParams\.set\("slide"/);
  assert.match(apiSource, /type PresentationOutputMode = "structured" \| "html" \| "slidev"/);
  assert.match(apiSource, /getLatestSessionPresentationSlidev/);
  assert.match(apiSource, /saveLatestSessionSlidevPresentation/);
});
