import { createRequire } from "module";
import fs from "fs";
import path from "path";

const require = createRequire(import.meta.url);
const archiver = require("archiver");
const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");

import { runRetrim } from "./results.service.js";

export async function createExportZip(jobId: string, clipIds: string[]) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const clipsDir = path.resolve(outputDir, "clips");
  const metadataDir = path.resolve(outputDir, "metadata");
  const thumbnailsDir = path.resolve(outputDir, "thumbnails");
  const translationsDir = path.resolve(outputDir, "translations");
  const zipPath = path.resolve(outputDir, "export.zip");

  if (!outputDir.startsWith(path.resolve(storageRoot, "outputs"))) {
    throw new Error("Invalid export path.");
  }

  // Ensure output clips directory exists
  if (!fs.existsSync(clipsDir)) {
    fs.mkdirSync(clipsDir, { recursive: true });
  }

  // Load clips.json to find all target clip IDs if none specified
  const clipsJsonPath = path.resolve(outputDir, "clips.json");
  const clipsData = fs.existsSync(clipsJsonPath)
    ? JSON.parse(fs.readFileSync(clipsJsonPath, "utf-8"))
    : { clips: [] };
  const allClips: any[] = clipsData.clips || [];
  const targetClipIds = clipIds.length > 0 ? clipIds : allClips.map((c) => c.id);

  // Sequentially retrim any missing/invalidated clips
  for (const clipId of targetClipIds) {
    const clipFile = path.join(clipsDir, `${clipId}.mp4`);
    if (!fs.existsSync(clipFile)) {
      try {
        await runRetrim(jobId, clipId);
      } catch (err) {
        console.error(`Failed to re-trim clip ${clipId} during zip export:`, err);
      }
    }
  }

  await new Promise<void>((resolve, reject) => {
    const output = fs.createWriteStream(zipPath);
    const archive = archiver("zip", { zlib: { level: 9 } });
    const selected = new Set(clipIds);
    const shouldInclude = (file: string) =>
      selected.size === 0 || selected.has(path.parse(file).name);

    output.on("close", resolve);
    archive.on("error", reject);
    archive.pipe(output);

    if (fs.existsSync(clipsDir)) {
      for (const file of fs.readdirSync(clipsDir).filter(shouldInclude)) {
        archive.file(path.join(clipsDir, file), { name: `clips/${file}` });
      }
    }

    if (fs.existsSync(metadataDir)) {
      for (const file of fs.readdirSync(metadataDir).filter(shouldInclude)) {
        archive.file(path.join(metadataDir, file), { name: `metadata/${file}` });
      }
    }

    if (fs.existsSync(thumbnailsDir)) {
      for (const file of fs.readdirSync(thumbnailsDir).filter(shouldInclude)) {
        archive.file(path.join(thumbnailsDir, file), { name: `thumbnails/${file}` });
      }
    }

    if (fs.existsSync(translationsDir)) {
      for (const language of fs.readdirSync(translationsDir)) {
        const languageDir = path.join(translationsDir, language);
        if (!fs.statSync(languageDir).isDirectory()) continue;
        for (const file of fs.readdirSync(languageDir).filter(shouldInclude)) {
          archive.file(path.join(languageDir, file), {
            name: `translations/${language}/${file}`
          });
        }
      }
    }

    archive.finalize();
  });

  return zipPath;
}
