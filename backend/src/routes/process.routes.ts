import fs from "fs";
import path from "path";
import { exec } from "child_process";
import { Router } from "express";
import { cancelPipeline, startPipeline, activeProcesses } from "../services/python.service.js";
import { readProject } from "../services/project.service.js";

export const processRouter = Router();

function getFreeSpace(dirPath: string): Promise<number> {
  return new Promise((resolve) => {
    const absolutePath = path.resolve(dirPath);
    const parsed = path.parse(absolutePath);
    const drive = parsed.root;

    if (process.platform === "win32") {
      const driveLetter = drive.slice(0, 2); // "C:"
      exec(`wmic logicaldisk where "DeviceID='${driveLetter}'" get FreeSpace`, (error, stdout) => {
        if (error) {
          exec(`powershell -Command "(Get-Volume -DriveLetter ${driveLetter[0]}).SizeRemaining"`, (err, out) => {
            if (err) {
              resolve(10 * 1024 * 1024 * 1024); // Fallback: 10GB
            } else {
              const bytes = parseInt(out.trim(), 10);
              resolve(isNaN(bytes) ? 10 * 1024 * 1024 * 1024 : bytes);
            }
          });
        } else {
          const lines = stdout.trim().split(/\r?\n/);
          if (lines.length > 1) {
            const bytes = parseInt(lines[1].trim(), 10);
            resolve(isNaN(bytes) ? 10 * 1024 * 1024 * 1024 : bytes);
          } else {
            resolve(10 * 1024 * 1024 * 1024);
          }
        }
      });
    } else {
      exec(`df -k "${absolutePath}"`, (error, stdout) => {
        if (error) {
          resolve(10 * 1024 * 1024 * 1024); // Fallback: 10GB
        } else {
          const lines = stdout.trim().split(/\r?\n/);
          if (lines.length > 1) {
            const parts = lines[1].replace(/\s+/g, " ").split(" ");
            const availableKB = parseInt(parts[3], 10);
            resolve(isNaN(availableKB) ? 10 * 1024 * 1024 * 1024 : availableKB * 1024);
          } else {
            resolve(10 * 1024 * 1024 * 1024);
          }
        }
      });
    }
  });
}

processRouter.post("/", async (request, response) => {
  const { jobId, settings } = request.body;

  if (!jobId) {
    response.status(400).json({ message: "Upload a video before processing." });
    return;
  }

  const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");
  const uploadDir = path.join(storageRoot, "uploads", jobId);

  if (!fs.existsSync(uploadDir)) {
    response.status(400).json({ message: "Upload directory not found." });
    return;
  }

  const files = fs.readdirSync(uploadDir);
  const videoFile = files.find((file) =>
    [".mp4", ".mov", ".avi", ".mkv", ".webm"].includes(path.extname(file).toLowerCase())
  );

  if (!videoFile) {
    response.status(400).json({ message: "No source video found in upload directory." });
    return;
  }

  const videoPath = path.join(uploadDir, videoFile);
  const videoSize = fs.statSync(videoPath).size;
  const requiredSpace = videoSize * 2;

  try {
    const freeSpace = await getFreeSpace(storageRoot);
    if (freeSpace < requiredSpace) {
      response.status(400).json({
        message: `Insufficient disk space. Required: ${(requiredSpace / (1024 * 1024)).toFixed(1)} MB, Available: ${(freeSpace / (1024 * 1024)).toFixed(1)} MB.`
      });
      return;
    }
  } catch {
    // Continue if space check fails to avoid blocking processing
  }

  const pipelineProcess = startPipeline(jobId, settings ?? {});

  response.status(202).json({
    jobId,
    pid: pipelineProcess.pid,
    message: "Processing started."
  });
});

processRouter.post("/:jobId/cancel", (request, response) => {
  const cancelled = cancelPipeline(request.params.jobId);

  response.status(cancelled ? 200 : 404).json({
    jobId: request.params.jobId,
    message: cancelled ? "Processing cancelled." : "No active process found."
  });
});

processRouter.get("/:jobId/status", (request, response) => {
  const { jobId } = request.params;
  const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");
  const uploadDir = path.join(storageRoot, "uploads", jobId);
  const tempDir = path.join(storageRoot, "temp", jobId);
  const outputDir = path.join(storageRoot, "outputs", jobId);

  if (!fs.existsSync(uploadDir)) {
    response.status(200).json({ exists: false });
    return;
  }

  // 1. Check if currently running
  const running = activeProcesses.has(jobId);

  // 2. Read completed stages from checkpoint.json
  const checkpointPath = path.join(tempDir, "checkpoint.json");
  let completedStages: string[] = [];
  if (fs.existsSync(checkpointPath)) {
    try {
      const checkpointData = JSON.parse(fs.readFileSync(checkpointPath, "utf-8"));
      completedStages = checkpointData.completed || [];
    } catch {}
  }

  // 3. Check if complete (meaning stage_13_thumbnails is completed and process is not running)
  const isComplete = !running && completedStages.includes("stage_13_thumbnails");
  const clipsJsonPath = path.join(outputDir, "clips.json");
  
  if (isComplete && fs.existsSync(clipsJsonPath)) {
    try {
      const clipsData = JSON.parse(fs.readFileSync(clipsJsonPath, "utf-8"));
      response.status(200).json({
        exists: true,
        status: "complete",
        percent: 100,
        clips: clipsData.clips || []
      });
      return;
    } catch {
      // JSON read/parse failed, proceed
    }
  }

  // Define total stages list matching Python pipeline and frontend store (20 canonical stages)
  const totalStagesList = [
    "stage_01_audio",
    "stage_02_vad",
    "stage_03_transcription",
    "stage_03_speaker_diarization",
    "stage_04_highlights",
    "stage_05_scene_detection",
    "stage_06_face_detection",
    "stage_07_face_tracking",
    "stage_07_subject_identity",
    "stage_08_shot_selection",
    "stage_08b_anchor_stream",
    "stage_08c_camera_operator",
    "stage_08d_transition_planner",
    "stage_09_cut_crop",
    "stage_10_captions",
    "stage_11_metadata",
    "stage_12_export",
    "stage_15_translation",
    "stage_14_music",
    "stage_13_thumbnails"
  ];
  
  const stageLabels: Record<string, string> = {
    stage_01_audio: "Audio extraction",
    stage_02_vad: "Voice activity detection",
    stage_03_transcription: "Transcription",
    stage_03_speaker_diarization: "Speaker diarization",
    stage_04_highlights: "Highlight detection",
    stage_05_scene_detection: "Scene detection",
    stage_06_face_detection: "Face detection",
    stage_07_face_tracking: "Face tracking",
    stage_07_subject_identity: "Subject identity continuity",
    stage_08_shot_selection: "Editorial shot selection",
    stage_08b_anchor_stream: "Per-frame anchor stream",
    stage_08c_camera_operator: "Spring-damped camera operator",
    stage_08d_transition_planner: "Smooth editorial transitions",
    stage_09_cut_crop: "Video cut and crop",
    stage_10_captions: "Caption generation",
    stage_11_metadata: "Metadata generation",
    stage_12_export: "Export preparation",
    stage_15_translation: "Translation",
    stage_14_music: "Background music",
    stage_13_thumbnails: "Thumbnail generation"
  };

  const totalStages = totalStagesList.length;
  const percent = Math.floor((completedStages.length / totalStages) * 100);

  // Read logs from pipeline.log
  let errorMessage: string | undefined = undefined;
  const logPath = path.join(tempDir, "pipeline.log");
  let logs: string[] = [];
  if (fs.existsSync(logPath)) {
    try {
      const content = fs.readFileSync(logPath, "utf-8");
      const lines = content.split(/\r?\n/).filter(Boolean);
      const lastLines = lines.slice(-80);
      logs = lastLines.map((line) => {
        try {
          const event = JSON.parse(line);
          if (event.type === "progress") {
            return `${event.percent}% ${event.message}`;
          } else if (event.type === "error") {
            return `Error: ${event.message}`;
          }
          return line;
        } catch {
          return line;
        }
      });
      // Extract error message for failed stage callout
      for (const logLine of logs.slice().reverse()) {
        if (logLine.toLowerCase().includes("error") || logLine.includes("Exception") || logLine.includes("got an unexpected")) {
          errorMessage = logLine.replace(/^Error:\s*/, "").trim();
          break;
        }
      }
    } catch {}
  }

  // Read stored project metadata to determine actual project status
  const project = readProject(jobId);
  const projectStatus: string = project?.status || "uploading";

  // Determine pipeline status:
  // - "running" if process is actively executing
  // - "failed" if project is failed or log contains error and not running
  // - "interrupted" if processing was started previously
  let calculatedStatus: string = projectStatus;
  if (running) {
    calculatedStatus = "running";
  } else if (projectStatus === "failed" || (errorMessage && !isComplete)) {
    calculatedStatus = "failed";
  } else if (projectStatus === "processing" || completedStages.length > 0) {
    calculatedStatus = "interrupted";
  }

  // Construct stages status
  let firstIncompleteFound = false;
  const stages = totalStagesList.map((id) => {
    const isCompleted = completedStages.includes(id);
    let stageStatus: "pending" | "running" | "complete" | "error" = "pending";
    let stagePercent = 0;
    let stageError: string | undefined = undefined;

    if (isCompleted) {
      stageStatus = "complete";
      stagePercent = 100;
    } else if (running && !firstIncompleteFound) {
      stageStatus = "running";
      stagePercent = 0;
      firstIncompleteFound = true;
    } else if (calculatedStatus === "failed" && !firstIncompleteFound) {
      stageStatus = "error";
      stagePercent = 0;
      stageError = errorMessage || "Stage execution encountered an error.";
      firstIncompleteFound = true;
    }

    return {
      id,
      label: stageLabels[id] || id,
      percent: stagePercent,
      status: stageStatus,
      ...(stageError ? { error: stageError } : {})
    };
  });

  response.status(200).json({
    exists: true,
    status: calculatedStatus,
    percent,
    stages,
    logs
  });
});

processRouter.post("/:jobId/resume", (request, response) => {
  const { jobId } = request.params;
  const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");
  const tempDir = path.join(storageRoot, "temp", jobId);
  const settingsPath = path.join(tempDir, "settings.json");

  // Check if running already
  if (activeProcesses.has(jobId)) {
    response.status(200).json({
      success: true,
      jobId,
      message: "Pipeline is already running."
    });
    return;
  }

  // Load saved settings
  let settings = {};
  if (fs.existsSync(settingsPath)) {
    try {
      settings = JSON.parse(fs.readFileSync(settingsPath, "utf-8"));
    } catch {}
  }

  const pipelineProcess = startPipeline(jobId, settings);

  response.status(202).json({
    success: true,
    jobId,
    pid: pipelineProcess.pid,
    message: "Resumed pipeline successfully."
  });
});
