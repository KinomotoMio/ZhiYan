import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PublicSharePlayerView } from "@/components/share/PublicSharePlayer";

test("public share player view renders loading state", () => {
  const html = renderToStaticMarkup(<PublicSharePlayerView loading />);
  assert.match(html, /正在加载演示/);
});

test("public share player view renders error state", () => {
  const html = renderToStaticMarkup(
    <PublicSharePlayerView errorMessage="分享链接无效或已失效" />
  );
  assert.match(html, /无法打开分享链接/);
  assert.match(html, /分享链接无效或已失效/);
});

test("public share player view renders centi-deck upgrade placeholder", () => {
  const html = renderToStaticMarkup(
    <PublicSharePlayerView
      playback={{
        title: "公开演示",
        outputMode: "slidev",
        presentation: null,
      }}
    />
  );

  assert.match(html, /公开演示/);
  assert.match(html, /centi-deck/);
});
