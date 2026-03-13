import { cpSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const sourcePath = path.resolve(__dirname, "../../shared/layout-metadata.json");
const targetDir = path.resolve(__dirname, "../src/generated");
const targetPath = path.join(targetDir, "layout-metadata.json");

mkdirSync(targetDir, { recursive: true });
cpSync(sourcePath, targetPath);
