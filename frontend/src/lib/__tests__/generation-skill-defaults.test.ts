import assert from "node:assert/strict";
import test from "node:test";

import { defaultSkillIdForOutputMode } from "@/lib/api";

test("default skill resolution prefers Slidev for markdown authoring", () => {
  assert.equal(defaultSkillIdForOutputMode("slidev"), "slidev-default");
});

test("default skill resolution maps HTML to html-default", () => {
  assert.equal(defaultSkillIdForOutputMode("html"), "html-default");
});

