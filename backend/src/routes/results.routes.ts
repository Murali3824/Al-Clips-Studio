import { Router } from "express";
import fs from "fs";
import path from "path";
import multer from "multer";
import {
  getClipPath,
  getThumbnailPath,
  getTranslatedClipPath,
  readResults,
  writeClipEdit,
  writeTrim,
  runRetrim,
  storageRoot
} from "../services/results.service.js";

const storagePathRoot = storageRoot;


export const resultsRouter = Router();

resultsRouter.get("/:jobId", (request, response) => {
  const results = readResults(request.params.jobId);

  if (!results) {
    response.status(404).json({ message: "Results not found." });
    return;
  }

  response.status(200).json(results);
});

resultsRouter.post("/:jobId/clips/:clipId/trim", (request, response) => {
  try {
    const { userStart, userEnd } = request.body;
    if (typeof userStart !== "number" || typeof userEnd !== "number") {
      response.status(400).json({ message: "Invalid userStart or userEnd parameters." });
      return;
    }
    const clip = writeTrim(request.params.jobId, request.params.clipId, userStart, userEnd);
    response.status(200).json({ success: true, clip });
  } catch (error: any) {
    response.status(500).json({ success: false, message: error.message });
  }
});

resultsRouter.post("/:jobId/clips/:clipId/edit", (request, response) => {
  try {
    const edits = request.body;
    if (!edits || typeof edits !== "object") {
      response.status(400).json({ message: "Invalid edit payload." });
      return;
    }
    const result = writeClipEdit(request.params.jobId, request.params.clipId, edits);
    response.status(200).json({ success: true, metadata: result });
  } catch (error: any) {
    response.status(500).json({ success: false, message: error.message });
  }
});

// POST /api/results/:jobId/clips/:clipId/render - Force render the clip and pipe progress events
resultsRouter.post("/:jobId/clips/:clipId/render", async (request, response) => {
  const { jobId, clipId } = request.params;
  try {
    // Force re-render by running retrim
    await runRetrim(jobId, clipId);
    response.status(200).json({ success: true });
  } catch (error: any) {
    response.status(500).json({ success: false, message: error.message });
  }
});

resultsRouter.get("/:jobId/clips/:clipId", async (request, response) => {
  const clipPath = await getClipPath(request.params.jobId, request.params.clipId);

  if (!clipPath) {
    response.status(404).json({ message: "Clip not found. Please click Save Changes to render the clip." });
    return;
  }

  response.sendFile(clipPath);
});

// GET /api/results/:jobId/clips/:clipId/download — force-download with Content-Disposition header
// The HTML download attribute is ignored for cross-origin requests (port 3000→3001),
// so we must set Content-Disposition: attachment server-side.
resultsRouter.get("/:jobId/clips/:clipId/download", async (request, response) => {
  const { jobId, clipId } = request.params;
  const clipPath = await getClipPath(jobId, clipId);

  if (!clipPath) {
    response.status(404).json({ message: "Clip not found. Please click Save Changes to render the clip first." });
    return;
  }

  // Resolve a human-readable filename from clips.json title if available
  let filename = `${clipId}.mp4`;
  try {
    const outputDir = path.resolve(storagePathRoot, "outputs", jobId);
    const clipsJson = path.resolve(outputDir, "clips.json");
    if (fs.existsSync(clipsJson)) {
      const data = JSON.parse(fs.readFileSync(clipsJson, "utf-8"));
      const clip = data.clips?.find((c: any) => c.id === clipId);
      if (clip?.title) {
        filename = `${clip.title.replace(/[^\w\s-]/g, "").replace(/\s+/g, "_").slice(0, 80)}.mp4`;
      }
    }
  } catch { /* fallback to clipId filename */ }

  response.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
  response.setHeader("Content-Type", "video/mp4");
  response.sendFile(clipPath);
});

resultsRouter.get("/:jobId/thumbnails/:clipId", async (request, response) => {
  const thumbnailPath = await getThumbnailPath(request.params.jobId, request.params.clipId);

  if (!thumbnailPath) {
    response.status(404).json({ message: "Thumbnail not found." });
    return;
  }

  response.sendFile(thumbnailPath);
});

resultsRouter.get("/:jobId/translations/:language/:clipId", (request, response) => {
  const translatedPath = getTranslatedClipPath(
    request.params.jobId,
    request.params.language,
    request.params.clipId
  );

  if (!translatedPath) {
    response.status(404).json({ message: "Translated clip not found." });
    return;
  }

  response.sendFile(translatedPath);
});

// Helper: resolve directory for asset type ('music' -> storage/music, others -> storage/assets/:type)
function getAssetDir(type: string): string {
  if (type === "music") {
    return path.resolve(storageRoot, "music");
  }
  return path.resolve(storageRoot, "assets", type);
}

// Configure storage for custom asset uploads (memes, gameplay, music)
const assetStorage = multer.diskStorage({
  destination: (request, file, callback) => {
    const { type } = request.params;
    const dest = getAssetDir(type);
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    callback(null, dest);
  },
  filename: (request, file, callback) => {
    const cleanName = file.originalname.replace(/[^a-zA-Z0-9._-]/g, "_");
    callback(null, cleanName);
  }
});
const uploadAsset = multer({ storage: assetStorage });

// GET /api/results/assets/:type - Browse asset files
resultsRouter.get("/assets/:type", (request, response) => {
  const { type } = request.params;
  const dir = getAssetDir(type);
  if (!fs.existsSync(dir)) {
    response.status(200).json([]);
    return;
  }
  try {
    const audioExts = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"];
    const files = fs.readdirSync(dir)
      .filter((file) => {
        if (file.startsWith(".")) return false;
        if (type === "music") {
          return audioExts.includes(path.extname(file).toLowerCase());
        }
        return true;
      })
      .map(file => ({
        name: file,
        url: `/api/results/assets/${type}/${file}`,
        path: path.join(dir, file)
      }));
    response.status(200).json(files);
  } catch (error: any) {
    response.status(500).json({ message: error.message });
  }
});

// POST /api/results/assets/:type - Upload a custom asset (meme/gameplay/music)
resultsRouter.post("/assets/:type", uploadAsset.single("file"), (request, response) => {
  if (!request.file) {
    response.status(400).json({ message: "No file uploaded." });
    return;
  }
  response.status(200).json({
    success: true,
    name: request.file.filename,
    url: `/api/results/assets/${request.params.type}/${request.file.filename}`,
    path: request.file.path
  });
});

// GET /api/results/assets/:type/:filename - Serve the uploaded custom asset
resultsRouter.get("/assets/:type/:filename", (request, response) => {
  const { type, filename } = request.params;
  const assetPath = path.join(getAssetDir(type), filename);
  if (fs.existsSync(assetPath)) {
    response.sendFile(assetPath);
  } else {
    response.status(404).json({ message: "Asset not found." });
  }
});
