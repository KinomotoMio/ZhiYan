import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));

function readFromLib(relativePath: string): string {
  return readFileSync(path.resolve(TEST_DIR, "..", relativePath), "utf8");
}

test("runtime exports CentiDeckRuntime class with mount/unmount/goTo", () => {
  const source = readFromLib("runtime.ts");
  assert.match(source, /export class CentiDeckRuntime/);
  assert.match(source, /mount\(/);
  assert.match(source, /unmount\(\)/);
  assert.match(source, /goTo\(/);
  assert.match(source, /next\(\)/);
  assert.match(source, /prev\(\)/);
});

test("runtime wires enter/leave lifecycle hooks", () => {
  const source = readFromLib("runtime.ts");
  assert.match(source, /module\.enter\?/);
  assert.match(source, /module\.leave\?/);
});

test("runtime exposes ctx.gsap + ctx.goTo + ctx.registerCleanup to slide modules", () => {
  const source = readFromLib("runtime.ts");
  assert.match(source, /gsap,/);
  assert.match(source, /goTo:/);
  assert.match(source, /registerCleanup:/);
});

test("loadModule registers gsap premium plugins once", () => {
  const source = readFromLib("loadModule.ts");
  assert.match(source, /Flip/);
  assert.match(source, /ScrollTrigger/);
  assert.match(source, /SplitText/);
  assert.match(source, /DrawSVGPlugin/);
  assert.match(source, /MorphSVGPlugin/);
  assert.match(source, /registerPlugin\(/);
  assert.match(source, /pluginsRegistered/);
});

test("loadModule uses blob URL + dynamic import and revokes afterwards", () => {
  const source = readFromLib("loadModule.ts");
  assert.match(source, /URL\.createObjectURL/);
  assert.match(source, /URL\.revokeObjectURL/);
  assert.match(source, /import\(/);
});

test("loadModule enforces strict-mode preamble on module source", () => {
  const source = readFromLib("loadModule.ts");
  assert.match(source, /prefixWithStrictPreamble/);
  assert.match(source, /"use strict"/);
});

test("types module declares CentiDeckSlideModule contract", () => {
  const source = readFromLib("types.ts");
  assert.match(source, /CentiDeckSlideModule/);
  assert.match(source, /render:/);
  assert.match(source, /enter\?:/);
  assert.match(source, /leave\?:/);
  assert.match(source, /actions\?:/);
  assert.match(source, /drilldowns\?:/);
});

test("theme helper returns cleanup closure", () => {
  const source = readFromLib("theme.ts");
  assert.match(source, /applyCentiDeckTheme/);
  assert.match(source, /setProperty/);
  assert.match(source, /removeProperty/);
});

test("index re-exports the public API surface", () => {
  const source = readFromLib("index.ts");
  assert.match(source, /export \{ CentiDeckRuntime \}/);
  assert.match(source, /loadAllCentiDeckModules/);
  assert.match(source, /applyCentiDeckTheme/);
  assert.match(source, /CentiDeckSlideModule/);
});
