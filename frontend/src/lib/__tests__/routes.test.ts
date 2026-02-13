import assert from "node:assert/strict";
import test from "node:test";

import { getSessionEditorPath } from "@/lib/routes";

test("getSessionEditorPath returns canonical session editor route", () => {
  assert.equal(getSessionEditorPath("abc"), "/sessions/abc/editor");
});

