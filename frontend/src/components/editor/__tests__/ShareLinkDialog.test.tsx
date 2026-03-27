import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ShareLinkDialogPanel } from "@/components/editor/ShareLinkDialog";

test("share link dialog renders stable link actions", () => {
  const html = renderToStaticMarkup(
    <ShareLinkDialogPanel
      shareUrl="https://example.com/share/token-123"
      onCopy={() => {}}
      onClose={() => {}}
    />
  );

  assert.match(html, /https:\/\/example\.com\/share\/token-123/);
  assert.match(html, /复制链接/);
  assert.match(html, /打开链接/);
});

test("share link dialog renders loading state copy", () => {
  const html = renderToStaticMarkup(
    <ShareLinkDialogPanel
      shareUrl=""
      loading
      onCopy={() => {}}
      onClose={() => {}}
    />
  );

  assert.match(html, /正在生成分享链接/);
});
