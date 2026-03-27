import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import MarkdownMessage from "@/components/chat/MarkdownMessage";

test("renders github-flavored markdown as semantic html", () => {
  const html = renderToStaticMarkup(
    <MarkdownMessage
      content={`### 大纲预览

---

| 页 | 标题 |
| --- | --- |
| 1 | **开场** |

- 要点 A
- 要点 B`}
    />
  );

  assert.match(html, /<h3/);
  assert.match(html, /<hr/);
  assert.match(html, /<table/);
  assert.match(html, /<strong[^>]*>开场<\/strong>/);
  assert.match(html, /<ul/);
  assert.doesNotMatch(html, /\| 页 \| 标题 \|/);
  assert.doesNotMatch(html, /node="\[object Object\]"/);
});
