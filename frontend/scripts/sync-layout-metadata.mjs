import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const targetDir = path.resolve(__dirname, "../src/generated");
mkdirSync(targetDir, { recursive: true });

const filesToSync = [
  ["../../shared/layout-metadata.json", "layout-metadata.json"],
  ["../../shared/fallback-semantics.json", "fallback-semantics.json"],
];

for (const [sourceRelativePath, targetFileName] of filesToSync) {
  const sourcePath = path.resolve(__dirname, sourceRelativePath);
  const targetPath = path.join(targetDir, targetFileName);
  writeFileSync(targetPath, readFileSync(sourcePath));
}
