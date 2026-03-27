import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import SpeakerNotes from "@/components/slides/SpeakerNotes";

test("speaker notes panel renders placeholder and keeps read-aloud disabled when empty", () => {
  const html = renderToStaticMarkup(
    <SpeakerNotes
      value=""
      onChange={() => {}}
      onSave={() => {}}
      onGenerateCurrent={() => {}}
      onGenerateAll={() => {}}
    />
  );

  assert.match(html, /Speaker Notes/);
  assert.match(html, /演讲者注解/);
  assert.match(html, /placeholder="输入当前页的演讲提示/);
  assert.match(html, />保存</);
  assert.match(html, />生成当前页</);
  assert.match(html, />生成全部</);
  assert.match(html, /title="朗读注解"/);
  assert.match(html, /<button type="button" disabled=""/);
  assert.doesNotMatch(html, /当前页还没有演讲者注解/);
  assert.doesNotMatch(html, /0 字/);
});

test("speaker notes panel renders note content and status copy", () => {
  const html = renderToStaticMarkup(
    <SpeakerNotes
      value="demo note"
      onChange={() => {}}
      onSave={() => {}}
      onGenerateCurrent={() => {}}
      onGenerateAll={() => {}}
      onPlayAudio={async () => new Blob(["audio"], { type: "audio/mpeg" })}
      isSaving
      generatingScope="all"
    />
  );

  assert.match(html, />demo note</);
  assert.match(html, /正在保存/);
  assert.match(html, /生成中/);
  assert.match(html, /保存中/);
  assert.match(html, /9 字/);
  assert.doesNotMatch(html, /title="朗读注解" disabled=""/);
});
