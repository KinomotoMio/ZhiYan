import assert from "node:assert/strict";
import test from "node:test";

import {
  createTempFileEntry,
  createTempTextEntry,
  createTempUrlEntry,
  describeAssetEntryStatus,
  getDeletableIds,
  markTempEntryError,
  mergeAssetEntries,
  updateTempEntryProgress,
} from "@/components/assets/assets-view-model";
import type { SourceMeta } from "@/types/source";

test("file upload temp entry exposes progress state", () => {
  const entry = createTempFileEntry(new File(["hello"], "report.pdf", { type: "application/pdf" }));
  const progressed = updateTempEntryProgress([entry], entry.key, 42)[0];

  assert.equal(entry.isTemp, true);
  assert.equal(entry.source.status, "uploading");
  assert.equal(entry.source.fileCategory, "pdf");
  assert.equal(describeAssetEntryStatus(progressed), "上传中 42%");
});

test("url and text temp entries keep retry payloads and error state", () => {
  const urlEntry = createTempUrlEntry("https://example.com");
  const textEntry = createTempTextEntry("纪要", "第一段\n第二段");
  const failed = markTempEntryError([urlEntry, textEntry], urlEntry.key, "抓取失败");

  assert.equal(urlEntry.retryPayload?.kind, "url");
  assert.equal(textEntry.retryPayload?.kind, "text");
  assert.equal(failed[0]?.source.status, "error");
  assert.equal(failed[0]?.source.error, "抓取失败");
});

test("mergeAssetEntries filters temp and persisted items together", () => {
  const persisted: SourceMeta[] = [
    {
      id: "src-1",
      name: "Alpha 报告",
      type: "file",
      fileCategory: "pdf",
      status: "ready",
      created_at: "2026-04-17T10:00:00.000Z",
      linked_session_count: 2,
    },
    {
      id: "src-2",
      name: "Beta 网址",
      type: "url",
      status: "ready",
      created_at: "2026-04-17T09:00:00.000Z",
      linked_session_count: 0,
    },
  ];
  const tempText = createTempTextEntry("Alpha 纪要", "摘要");
  const merged = mergeAssetEntries({
    persistedItems: persisted,
    tempEntries: [tempText],
    query: "Alpha",
    typeFilter: "all",
    statusFilter: "all",
    sort: "linked_desc",
  });

  assert.equal(merged.length, 2);
  assert.equal(merged[0]?.source.id, "src-1");
  assert.equal(merged[1]?.source.name, "Alpha 纪要");
  assert.deepEqual(getDeletableIds(merged), ["src-1"]);
});
