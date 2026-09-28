import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const html = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(
  (match) => match[1],
);

scripts.forEach((script, index) => {
  try {
    new Function(script);
  } catch (error) {
    throw new Error(`inline script ${index}: ${error.message}`);
  }
});

if (!html.includes("invokeDesktop('extract_document'")) {
  throw new Error("Tauri OCR command is missing");
}
if (!html.includes("invokeDesktop('export_document'")) {
  throw new Error("Tauri export command is missing");
}
for (const id of [
  "univProfessorUni", "univProfessorCol", "univAssociateUni", "univAssociateCol",
  "univAssistantUni", "univAssistantCol", "univJoGyoUni", "univJoGyoCol",
]) {
  if (html.includes(`id:"${id}"`)) {
    throw new Error(`National university faculty qualification is still selectable: ${id}`);
  }
}

console.log(`inlineScripts=${scripts.length} syntax=ok tauriCommands=ok`);
