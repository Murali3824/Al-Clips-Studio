import fs from "fs";
import path from "path";

export const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");

function normalizeScore(val: any, fieldName: string, clipId: string): number | null {
  if (val === undefined || val === null) {
    return null;
  }
  if (typeof val !== "number" && typeof val !== "string") {
    console.error(`[Pipeline Integrity Error] Clip ${clipId} metric '${fieldName}' has invalid type '${typeof val}'.`);
    return null;
  }
  const n = Number(val);
  if (isNaN(n) || !isFinite(n)) {
    console.error(`[Pipeline Integrity Error] Clip ${clipId} metric '${fieldName}' is NaN or Infinity.`);
    return null;
  }
  if (n > 0 && n <= 1.0) {
    return Math.round(n * 100);
  }
  const intVal = Math.round(n);
  return Math.max(0, Math.min(100, intVal));
}

function verifyPipelineIntegrity(
  clipId: string,
  clipData: Record<string, any>,
  metadata: Record<string, any>,
  normalizedScores: Record<string, number | null>
): void {
  const requiredFields = [
    "hookScore",
    "retentionScore",
    "emotionalImpact",
    "productionScore",
    "seoScore",
    "viralScore",
    "score"
  ];

  for (const field of requiredFields) {
    if (!(field in metadata) && !(field in clipData)) {
      console.error(`[Pipeline Integrity Error] Clip ${clipId} is missing required field '${field}'. Check pipeline schema definition.`);
    } else if (normalizedScores[field] === null) {
      console.warn(`[Pipeline Integrity Warning] Clip ${clipId} has null value for '${field}'. Check the AI pipeline stage responsible for generating this metric.`);
    }
  }

  for (const [key, val] of Object.entries(normalizedScores)) {
    if (val !== null) {
      if (!Number.isInteger(val) || val < 0 || val > 100) {
        console.error(`[Pipeline Integrity Error] Clip ${clipId} metric '${key}' has invalid value: ${val}`);
      }
    }
  }

  for (const field of requiredFields) {
    if (field in clipData && field in metadata && field !== "score") {
      const clipVal = normalizeScore(clipData[field], field, clipId);
      const metaVal = normalizedScores[field];
      if (clipVal !== null && metaVal !== null && clipVal !== metaVal) {
        console.error(`[Cross-Artifact Consistency Error] Clip ${clipId} field '${field}' mismatch between clips.json (${clipVal}) and metadata.json (${metaVal}). Downstream stage mutated score.`);
      }
    }
  }
}

export function readResults(jobId: string) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const resultsPath = path.resolve(outputDir, "clips.json");
  const metadataDir = path.resolve(outputDir, "metadata");
  const translationsPath = path.resolve(outputDir, "translations.json");
  const transcriptPath = path.resolve(storageRoot, "temp", jobId, "transcript.json");

  if (!resultsPath.startsWith(outputDir) || !fs.existsSync(resultsPath)) {
    return null;
  }

  const results = JSON.parse(fs.readFileSync(resultsPath, "utf-8"));
  const translations = fs.existsSync(translationsPath)
    ? JSON.parse(fs.readFileSync(translationsPath, "utf-8"))
    : { clips: [] };

  const transcript = fs.existsSync(transcriptPath)
    ? JSON.parse(fs.readFileSync(transcriptPath, "utf-8"))
    : { words: [] };
  const allWords = transcript.words || [];

  const clips = results.clips.map((clip: Record<string, any>) => {
    const metadataPath = path.resolve(metadataDir, `${clip.id}.json`);
    const metadata = fs.existsSync(metadataPath)
      ? JSON.parse(fs.readFileSync(metadataPath, "utf-8"))
      : {};

    const clipStart = Number(clip.start);
    const clipEnd = Number(clip.end);
    const clipWords = allWords
      .filter((w: any) => Number(w.end) > clipStart && Number(w.start) < clipEnd)
      .map((w: any) => ({
        word: String(w.word),
        start: Number(w.start) - clipStart,
        end: Number(w.end) - clipStart
      }));

    // Canonical score is clip.score (Stage 04 AI content quality), fallback to metadata.score
    const rawScore = clip.score ?? metadata.score;
    const normalizedScores: Record<string, number | null> = {
      score: normalizeScore(rawScore, "score", clip.id),
      hookScore: normalizeScore(clip.hookScore ?? metadata.hookScore, "hookScore", clip.id),
      retentionScore: normalizeScore(clip.retentionScore ?? metadata.retentionScore, "retentionScore", clip.id),
      emotionalImpact: normalizeScore(clip.emotionalImpact ?? metadata.emotionalImpact, "emotionalImpact", clip.id),
      productionScore: normalizeScore(clip.productionScore ?? metadata.productionScore, "productionScore", clip.id),
      seoScore: normalizeScore(metadata.seoScore ?? clip.seoScore, "seoScore", clip.id),
      viralScore: normalizeScore(clip.viralScore ?? clip.score ?? metadata.viralScore ?? rawScore, "viralScore", clip.id),
    };

    verifyPipelineIntegrity(clip.id, clip, metadata, normalizedScores);

    const effectiveHook = metadata.userHookText || metadata.autoHookText || metadata.hookText || metadata.hook || "";

    delete metadata.suggestedPostingTime;
    delete metadata.mood;
    delete metadata.topics;
    delete metadata.keyTopics;
    delete metadata.emotion;

    let endThumbnail = clip.endThumbnail ?? null;
    if (endThumbnail && typeof endThumbnail === "object" && endThumbnail.imagePath) {
      const filename = path.basename(endThumbnail.imagePath);
      endThumbnail = {
        ...endThumbnail,
        url: `/api/results/${jobId}/end-thumbnail/${filename}`
      };
    }

    return {
      ...clip,
      endThumbnail,
      mediaUrl: `/api/results/${jobId}/clips/${clip.id}`,
      thumbnailUrl: `/api/results/${jobId}/thumbnails/${clip.id}`,
      translations: translations.clips
        .filter((item: Record<string, unknown>) => item.clipId === clip.id)
        .map((item: Record<string, unknown>) => ({
          language: item.language,
          mediaUrl: `/api/results/${jobId}/translations/${item.language}/${clip.id}`
        })),
      duration: clipEnd - clipStart,
      words: clipWords,
      ...metadata,
      autoHookText: effectiveHook,
      ...normalizedScores
    };
  });

  return { jobId, clips };
}

export async function saveEndThumbnail(jobId: string, clipId: string, file: Express.Multer.File) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const thumbnailsDir = path.resolve(outputDir, "thumbnails");
  if (!fs.existsSync(thumbnailsDir)) {
    fs.mkdirSync(thumbnailsDir, { recursive: true });
  }

  const ext = path.extname(file.originalname) || ".png";
  const filename = `end_thumbnail_${clipId}${ext}`;
  const targetPath = path.resolve(thumbnailsDir, filename);

  fs.copyFileSync(file.path, targetPath);
  try { fs.unlinkSync(file.path); } catch { /* ignore */ }

  const relPath = `thumbnails/${filename}`;

  const resultsPath = path.resolve(outputDir, "clips.json");
  if (!fs.existsSync(resultsPath)) {
    throw new Error("clips.json not found");
  }

  const results = JSON.parse(fs.readFileSync(resultsPath, "utf-8"));
  const clip = results.clips.find((c: any) => c.id === clipId);
  if (!clip) {
    throw new Error("clip not found");
  }

  const endThumbnailObj = {
    enabled: true,
    imagePath: relPath
  };

  clip.endThumbnail = endThumbnailObj;
  fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));

  const rawPath = path.resolve(storageRoot, "temp", jobId, `${clipId}_raw_retrim.mp4`);
  if (fs.existsSync(rawPath)) fs.unlinkSync(rawPath);

  runRetrim(jobId, clipId).catch((err) => {
    console.error(`[EndThumbnail Error] retrim failed for clip ${clipId}:`, err);
  });

  return {
    ...endThumbnailObj,
    url: `/api/results/${jobId}/end-thumbnail/${filename}`
  };
}

export async function removeEndThumbnail(jobId: string, clipId: string) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const resultsPath = path.resolve(outputDir, "clips.json");
  if (!fs.existsSync(resultsPath)) {
    throw new Error("clips.json not found");
  }

  const results = JSON.parse(fs.readFileSync(resultsPath, "utf-8"));
  const clip = results.clips.find((c: any) => c.id === clipId);
  if (!clip) {
    throw new Error("clip not found");
  }

  if (clip.endThumbnail && clip.endThumbnail.imagePath) {
    const fullPath = path.resolve(outputDir, clip.endThumbnail.imagePath);
    if (fs.existsSync(fullPath)) {
      try { fs.unlinkSync(fullPath); } catch { /* ignore */ }
    }
  }

  clip.endThumbnail = null;
  fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));

  const rawPath = path.resolve(storageRoot, "temp", jobId, `${clipId}_raw_retrim.mp4`);
  if (fs.existsSync(rawPath)) fs.unlinkSync(rawPath);

  runRetrim(jobId, clipId).catch((err) => {
    console.error(`[EndThumbnail Error] retrim failed after removal for clip ${clipId}:`, err);
  });

  return { success: true };
}

import { spawn } from "child_process";
import { io } from "../server.js";

// Guard against concurrent retrim processes for the same clip
const retrimInProgress = new Set<string>();

export function runRetrim(jobId: string, clipId: string): Promise<void> {
  const lockKey = `${jobId}:${clipId}`;

  // If already running, wait for it to complete instead of spawning a second process
  if (retrimInProgress.has(lockKey)) {
    return new Promise((resolve, reject) => {
      const interval = setInterval(() => {
        if (!retrimInProgress.has(lockKey)) {
          clearInterval(interval);
          resolve();
        }
      }, 500);
      // Timeout after 5 minutes
      setTimeout(() => {
        clearInterval(interval);
        reject(new Error("Retrim timed out waiting for in-progress render to complete."));
      }, 300_000);
    });
  }

  retrimInProgress.add(lockKey);

  return new Promise((resolve, reject) => {
    const root = path.resolve(process.cwd(), "..");
    const scriptPath = path.join(root, "ai", "pipeline", "retrim.py");

    // Pre-flight: verify upload directory and source video exist
    const uploadDir = path.resolve(storageRoot, "uploads", jobId);
    if (!fs.existsSync(uploadDir)) {
      retrimInProgress.delete(lockKey);
      reject(new Error(`Original uploaded video not found. The upload directory for job "${jobId}" no longer exists. Please re-upload the video.`));
      return;
    }
    const videoFiles = fs.readdirSync(uploadDir).filter((f: string) => /\.(mp4|mov|mkv|avi|webm|wmv|flv)$/i.test(f));
    if (videoFiles.length === 0) {
      retrimInProgress.delete(lockKey);
      reject(new Error(`No source video found in upload directory for job "${jobId}". The original video may have been deleted.`));
      return;
    }

    // Pass STORAGE_PATH so retrim.py resolves the same storage directory
    const child = spawn("python", ["-u", scriptPath, "--job-id", jobId, "--clip-id", clipId], {
      cwd: root,
      env: { ...process.env, PYTHONUNBUFFERED: "1", STORAGE_PATH: storageRoot }
    });

    child.stdout.on("data", (chunk) => {
      const dataStr = chunk.toString();
      for (const line of dataStr.split(/\r?\n/).filter(Boolean)) {
        try {
          const progressObj = JSON.parse(line);
          if (progressObj && (progressObj.progress !== undefined || progressObj.stage !== undefined)) {
            io.emit("retrim:progress", { jobId, clipId, ...progressObj });
          }
        } catch {
          // Plain log line
          io.emit("retrim:log", { jobId, clipId, message: line });
        }
      }
    });

    let stderr = "";
    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      retrimInProgress.delete(lockKey);
      if (code === 0) {
        io.emit("retrim:progress", { jobId, clipId, stage: "Complete", progress: 100 });
        resolve();
      } else {
        let friendlyMsg = `Retrim failed (exit code ${code}).`;
        if (stderr.includes("FileNotFoundError")) {
          friendlyMsg = "Original uploaded video could not be found. Please re-upload the video and try again.";
        } else if (stderr.includes("No video found")) {
          friendlyMsg = "Source video file is missing from the upload directory.";
        } else if (stderr.length > 0) {
          const lines = stderr.trim().split("\n").filter(Boolean);
          const lastLine = lines[lines.length - 1];
          if (lastLine.length < 200) {
            friendlyMsg = lastLine;
          }
        }
        reject(new Error(friendlyMsg));
      }
    });
  });
}

export function writeTrim(jobId: string, clipId: string, userStart: number, userEnd: number) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const resultsPath = path.resolve(outputDir, "clips.json");

  if (!fs.existsSync(resultsPath)) {
    throw new Error("clips.json not found");
  }

  const results = JSON.parse(fs.readFileSync(resultsPath, "utf-8"));
  const clip = results.clips.find((c: any) => c.id === clipId);
  if (!clip) {
    throw new Error("clip not found");
  }

  clip.userStart = userStart;
  clip.userEnd = userEnd;
  clip.start = userStart;
  clip.end = userEnd;
  clip.duration = userEnd - userStart;

  fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));

  // NOTE: Do NOT delete the existing clip file here.
  // The clip continues to play from the old render until the user explicitly
  // clicks "Save Changes", which triggers the /render endpoint.
  // Only invalidate the raw retrim cache (layout encode) since timing changed.
  const rawPath = path.resolve(storageRoot, "temp", jobId, `${clipId}_raw_retrim.mp4`);
  if (fs.existsSync(rawPath)) fs.unlinkSync(rawPath);

  return clip;
}

export function writeClipEdit(jobId: string, clipId: string, edits: Record<string, unknown>) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const metadataDir = path.resolve(outputDir, "metadata");
  const metadataPath = path.resolve(metadataDir, `${clipId}.json`);

  if (!fs.existsSync(metadataDir)) {
    fs.mkdirSync(metadataDir, { recursive: true });
  }

  const existingMeta = fs.existsSync(metadataPath)
    ? JSON.parse(fs.readFileSync(metadataPath, "utf-8"))
    : {};

  // Editorial keys belong strictly to metadata/{clipId}.json
  const editorialKeys = new Set([
    "title", "hookText", "userHookText", "autoHookText", "hook",
    "description", "tags", "categorizedHashtags", "keywords",
    "niche", "category", "targetAudience", "mood", "suggestedPostingTime"
  ]);

  const metaEdits: Record<string, unknown> = {};
  const clipEdits: Record<string, unknown> = {};

  for (const [key, val] of Object.entries(edits)) {
    if (editorialKeys.has(key)) {
      metaEdits[key] = val;
    } else {
      clipEdits[key] = val;
    }
  }

  // Always update metadata/{clipId}.json with editorial edits (or all edits for compatibility)
  const mergedMeta = { ...existingMeta, ...edits };
  fs.writeFileSync(metadataPath, JSON.stringify(mergedMeta, null, 2));

  // Update clips.json for timeline / render settings
  const resultsPath = path.resolve(outputDir, "clips.json");
  if (fs.existsSync(resultsPath)) {
    const results = JSON.parse(fs.readFileSync(resultsPath, "utf-8"));
    const clip = results.clips.find((c: any) => c.id === clipId);
    if (clip) {
      if (typeof edits.userStart === "number" && typeof edits.userEnd === "number") {
        clip.userStart = edits.userStart;
        clip.userEnd = edits.userEnd;
        clip.start = edits.userStart;
        clip.end = edits.userEnd;
        clip.duration = Number(edits.userEnd) - Number(edits.userStart);
      }
      // Copy rendering fields to clip in clips.json
      const renderKeys = ["layoutMode", "blurStrength", "frameAspect", "autoHook", "captionDisplayMode", "highlightColorMode", "captionHighlightColor"];
      for (const rk of renderKeys) {
        if (rk in edits) clip[rk] = edits[rk];
      }
      // Strip editorial fields from clips.json if present
      delete clip.title;
      delete clip.hook;
      delete clip.autoHookText;
      delete clip.hookText;
      delete clip.userHookText;

      fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));
    }
  }

  // Invalidate raw retrim cache if timing or layout changes
  if (typeof edits.userStart === "number" || typeof edits.userEnd === "number" || ["layoutMode", "blurStrength", "frameAspect"].some((k) => k in edits)) {
    const rawPath = path.resolve(storageRoot, "temp", jobId, `${clipId}_raw_retrim.mp4`);
    if (fs.existsSync(rawPath)) fs.unlinkSync(rawPath);
  }

  // Invalidate rendered clip to trigger fresh retrim
  const clipPath = path.resolve(outputDir, "clips", `${clipId}.mp4`);
  if (fs.existsSync(clipPath)) fs.unlinkSync(clipPath);

  return mergedMeta;
}

export async function getClipPath(jobId: string, clipId: string) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const clipPath = path.resolve(outputDir, "clips", `${clipId}.mp4`);

  if (!clipPath.startsWith(outputDir)) {
    return null;
  }

  // Do NOT auto-retrim here. The /render endpoint is the only retrim trigger.
  // Auto-retrims on video GET caused race conditions with byte-range streaming requests.
  if (!fs.existsSync(clipPath)) {
    return null;
  }

  return clipPath;
}

export async function getThumbnailPath(jobId: string, clipId: string) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const thumbnailPath = path.resolve(outputDir, "thumbnails", `${clipId}.png`);

  if (!thumbnailPath.startsWith(outputDir)) {
    return null;
  }

  if (!fs.existsSync(thumbnailPath)) {
    // Only auto-retrim for missing thumbnails (not the main clip), and only if
    // a clip file exists (meaning a render has happened before).
    const clipPath = path.resolve(outputDir, "clips", `${clipId}.mp4`);
    if (fs.existsSync(clipPath)) {
      try {
        await runRetrim(jobId, clipId);
      } catch (e) {
        console.error("Retrim thumbnail error:", e);
        return null;
      }
    } else {
      return null;
    }
  }

  return thumbnailPath;
}

export function getTranslatedClipPath(jobId: string, language: string, clipId: string) {
  const outputDir = path.resolve(storageRoot, "outputs", jobId);
  const translatedPath = path.resolve(outputDir, "translations", language, `${clipId}.mp4`);

  if (!translatedPath.startsWith(outputDir) || !fs.existsSync(translatedPath)) {
    return null;
  }

  return translatedPath;
}
