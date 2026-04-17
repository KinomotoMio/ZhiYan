import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import AddSourceArea from "@/components/create/AddSourceArea";
import {
  canSubmitTextSource,
  getAvailableAddSourceModes,
  resetAddSourceAreaDrafts,
  resolveTextSourceName,
} from "@/components/create/add-source-area-logic";

test("renders text source controls when text submit is enabled", () => {
  const html = renderToStaticMarkup(
    <AddSourceArea
      onFilesSelected={() => {}}
      onUrlSubmit={() => {}}
      onTextSubmit={() => {}}
      defaultMode="text"
    />
  );

  assert.match(html, /新建文本素材/);
  assert.match(html, /素材名称（可选）/);
  assert.match(html, /保存文本/);
});

test("text submit button starts disabled without required fields", () => {
  const html = renderToStaticMarkup(
    <AddSourceArea
      onFilesSelected={() => {}}
      onUrlSubmit={() => {}}
      onTextSubmit={() => {}}
      defaultMode="text"
    />
  );

  assert.match(html, /保存文本/);
  assert.match(html, /disabled=""/);
});

test("text source helpers expose submit and reset behavior", () => {
  assert.deepEqual(getAvailableAddSourceModes(true), ["file", "url", "text"]);
  assert.equal(canSubmitTextSource("标题", "内容"), true);
  assert.equal(canSubmitTextSource("", "内容"), true);
  assert.equal(canSubmitTextSource("标题", "   "), false);
  assert.equal(resolveTextSourceName("  标题  ", "正文"), "标题");
  assert.equal(resolveTextSourceName("", "第一行标题\n第二行正文"), "第一行标题");
  assert.deepEqual(resetAddSourceAreaDrafts(), {
    mode: "file",
    urlValue: "",
    textName: "",
    textContent: "",
  });
});
