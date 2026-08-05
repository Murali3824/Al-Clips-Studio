import { Router } from "express";
import multer from "multer";
import fs from "fs";
import path from "path";
import { createJob } from "../services/job.service.js";
import { writeProject } from "../services/project.service.js";
import { validateVideoFile } from "../utils/fileValidation.js";
import { ensureJobUploadDir } from "../utils/storagePaths.js";
import {
  isValidYouTubeUrl,
  getVideoInfo,
  startYouTubeDownload,
  validateDependencies,
} from "../services/youtube.service.js";

export const uploadRouter = Router();

const storage = multer.diskStorage({
  destination: (request, _file, callback) => {
    const job = createJob();
    request.body.jobId = job.jobId;
    callback(null, ensureJobUploadDir(job.jobId));
  },
  filename: (_request, file, callback) => {
    const extension = file.originalname.split(".").pop()?.toLowerCase() ?? "mp4";
    callback(null, `input.${extension}`);
  }
});

const upload = multer({
  storage,
  fileFilter: (_request, file, callback) => {
    const result = validateVideoFile(file.originalname, file.mimetype);
    if (!result.ok) {
      callback(new Error(result.message));
      return;
    }
    callback(null, true);
  },
  limits: {
    fileSize: 10 * 1024 * 1024 * 1024
  }
});

// POST /api/upload — Local file upload
uploadRouter.post("/", upload.single("video"), (request, response) => {
  if (!request.file) {
    response.status(400).json({ message: "No video file uploaded." });
    return;
  }

  const { jobId } = request.body;
  const originalName = request.file.originalname;

  const defaultName = originalName
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    || originalName;

  writeProject(jobId, {
    name: defaultName,
    originalFileName: originalName,
    status: "uploading",
    storageBytes: request.file.size,
    clipCount: 0,
  });

  response.status(201).json({
    jobId,
    originalName,
    storedName: request.file.filename,
    size: request.file.size,
    mimetype: request.file.mimetype,
    uploadedAt: new Date().toISOString(),
    projectName: defaultName,
  });
});

// POST /api/upload/youtube — Import from YouTube URL
uploadRouter.post("/youtube", async (request, response) => {
  try {
    const { url } = request.body;
    if (!url || typeof url !== "string") {
      response.status(400).json({ message: "YouTube URL is required." });
      return;
    }

    if (!isValidYouTubeUrl(url)) {
      response.status(400).json({ message: "Invalid YouTube URL. Please enter a valid YouTube link." });
      return;
    }

    // Retrieve video metadata (non-blocking validation check)
    const info = await getVideoInfo(url);
    const job = createJob();
    const jobId = job.jobId;

    const projectName = info.title.trim() || "YouTube Video";

    // Create uploads/project.json metadata entry immediately
    writeProject(jobId, {
      name: projectName,
      originalFileName: `${projectName}.mp4`,
      status: "uploading",
      clipCount: 0,
    });

    // Fire off async download process
    startYouTubeDownload(jobId, url, projectName);

    response.status(201).json({
      jobId,
      originalName: `${projectName}.mp4`,
      projectName,
      duration: info.duration,
      thumbnailUrl: info.thumbnailUrl || null,
    });
  } catch (error: any) {
    response.status(500).json({ message: error.message || "Failed to initialize YouTube download." });
  }
});

// GET /api/upload/youtube/status — Check health of YouTube downloader dependencies
uploadRouter.get("/youtube/status", async (_request, response) => {
  try {
    const status = await validateDependencies();
    response.status(200).json(status);
  } catch (error: any) {
    response.status(500).json({ ok: false, issues: [error.message || "Failed to validate dependencies."] });
  }
});

// GET /api/upload/:jobId/video — Stream/serve the input source video file
uploadRouter.get("/:jobId/video", (request, response) => {
  try {
    const { jobId } = request.params;
    const uploadDir = ensureJobUploadDir(jobId);
    if (!fs.existsSync(uploadDir)) {
      response.status(404).json({ message: "Upload directory not found." });
      return;
    }
    const files = fs.readdirSync(uploadDir);
    const videoFile = files.find((file) =>
      [".mp4", ".mov", ".avi", ".mkv", ".webm"].includes(path.extname(file).toLowerCase())
    );
    if (!videoFile) {
      response.status(404).json({ message: "Video file not found in upload directory." });
      return;
    }
    const videoPath = path.resolve(uploadDir, videoFile);
    response.sendFile(videoPath, (err: any) => {
      if (err && !response.headersSent) {
        if (err.code === "ECONNRESET" || err.name === "RangeNotSatisfiableError" || err.status === 416) {
          response.status(416).end();
        } else {
          console.warn(`[sendFile Warning] ${videoPath}:`, err.message || err);
        }
      }
    });
  } catch (error: any) {
    response.status(500).json({ message: error.message || "Failed to stream video." });
  }
});
