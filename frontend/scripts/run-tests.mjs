import { readdirSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const srcDir = path.join(repoRoot, "src");
const tsxCliPath = path.join(repoRoot, "node_modules", "tsx", "dist", "cli.mjs");

function collectTestFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const resolved = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      return collectTestFiles(resolved);
    }

    return /\.test\.tsx?$/.test(entry.name) ? [resolved] : [];
  });
}

const testFiles = collectTestFiles(srcDir);

if (testFiles.length === 0) {
  process.exit(0);
}

const result = spawnSync(process.execPath, [tsxCliPath, "--test", ...testFiles], {
  cwd: repoRoot,
  stdio: "inherit",
});

if (result.error) {
  throw result.error;
}

process.exit(result.status ?? 1);
