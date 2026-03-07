import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { spawnSync } from "node:child_process";

const rootDir = process.cwd();
const srcDir = join(rootDir, "src");
const tsxCli = join(rootDir, "node_modules", "tsx", "dist", "cli.mjs");

function collectTestFiles(dir) {
  const entries = readdirSync(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const fullPath = join(dir, entry.name);

    if (entry.isDirectory()) {
      files.push(...collectTestFiles(fullPath));
      continue;
    }

    if (!entry.isFile()) {
      continue;
    }

    if (/\.test\.tsx?$/.test(entry.name)) {
      files.push(fullPath);
    }
  }

  return files;
}

if (!statSync(srcDir).isDirectory()) {
  console.error("Test source directory not found:", srcDir);
  process.exit(1);
}

const testFiles = collectTestFiles(srcDir).sort();

if (testFiles.length === 0) {
  console.log("No test files found under src");
  process.exit(0);
}

const result = spawnSync(process.execPath, [tsxCli, "--test", ...testFiles], {
  stdio: "inherit",
  cwd: rootDir,
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

if (typeof result.status === "number") {
  process.exit(result.status);
}

console.error(
  "Test runner exited without a status for files:",
  testFiles.map((file) => relative(rootDir, file)).join(", ")
);
process.exit(1);
