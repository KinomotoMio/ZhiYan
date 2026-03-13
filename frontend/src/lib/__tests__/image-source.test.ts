import assert from "node:assert/strict";
import test from "node:test";

import { getImageSource } from "@/lib/image-source";

test("getImageSource treats an empty prompt key as ai", () => {
  assert.equal(getImageSource({ prompt: "" }), "ai");
});
