import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_LOADING_TITLE,
  buildLoadingTitle,
  compactLoadingTitle,
  resolveGenerationRequestTitle,
} from "@/lib/loading-title";

test("compactLoadingTitle extracts a readable subject from a long prompt", () => {
  const title = compactLoadingTitle(
    "请基于以下内容生成一个关于人工智能对未来工作影响的10页PPT，需要适合管理层汇报。"
  );

  assert.equal(title, "人工智能对未来工作影响");
});

test("compactLoadingTitle trims prompt boilerplate and suffixes", () => {
  const title = compactLoadingTitle("设计一个针对寻求融资的初创公司提案演示文稿");

  assert.equal(title, "针对寻求融资的初创公司提案");
});

test("buildLoadingTitle falls back to source names or a generic loading label", () => {
  assert.equal(
    buildLoadingTitle({ topic: "", sourceNames: ["年度复盘-最终版-v6.pptx"] }),
    "年度复盘-最终版-v6"
  );
  assert.equal(
    buildLoadingTitle({ topic: "", sourceNames: ["a.pdf", "b.pdf"] }),
    "基于2个来源生成"
  );
  assert.equal(buildLoadingTitle({ topic: "", sourceNames: [] }), DEFAULT_LOADING_TITLE);
});

test("resolveGenerationRequestTitle prefers topic over stale request title", () => {
  const title = resolveGenerationRequestTitle({
    topic: "准备一个关于供应链优化的演示文稿，突出冷链、仓配协同和损耗控制。",
    title: "准备一个关于供应链优化的演示文稿，突出冷链、仓配协同和损耗控制。",
  });

  assert.equal(title, "供应链优化");
});
