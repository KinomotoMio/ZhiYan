import assert from "node:assert/strict";
import test from "node:test";

import { getExportSuccessMessage } from "@/lib/export-feedback";

test("getExportSuccessMessage keeps standard success copy for structured exports", () => {
  assert.equal(getExportSuccessMessage("pptx", "structured"), "PPTX 导出成功");
  assert.equal(getExportSuccessMessage("pdf"), "PDF 导出成功");
});

test("getExportSuccessMessage warns when PPTX used image fallback", () => {
  assert.equal(
    getExportSuccessMessage("pptx", "fallback-image"),
    "PPTX 已按图片兜底导出，视觉保真优先，但不保证可编辑性"
  );
});
