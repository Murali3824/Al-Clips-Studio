import { ChildProcessWithoutNullStreams, spawn } from "child_process";
import path from "path";
import fs from "fs";
import { io } from "../server.js";
import { writeProject } from "./project.service.js";

export const activeProcesses = new Map<string, ChildProcessWithoutNullStreams>();

export function startPipeline(jobId: string, settings: Record<string, unknown>) {
  cancelPipeline(jobId);

  const root = path.resolve(process.cwd(), "..");
  const tempDir = path.join(root, "storage", "temp", jobId);
  if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir, { recursive: true });
  }

  // Create job logs directory and root logs directory
  const jobLogsDir = path.join(tempDir, "logs");
  if (!fs.existsSync(jobLogsDir)) {
    fs.mkdirSync(jobLogsDir, { recursive: true });
  }
  const rootLogsDir = path.join(root, "logs");
  if (!fs.existsSync(rootLogsDir)) {
    fs.mkdirSync(rootLogsDir, { recursive: true });
  }

  const jobDebugLogPath = path.join(jobLogsDir, "debug.log");
  const rootDebugLogPath = path.join(rootLogsDir, "debug.log");

  // Reset debug log files for this run
  try { if (fs.existsSync(jobDebugLogPath)) fs.unlinkSync(jobDebugLogPath); } catch {}
  
  // Save settings.json for project recovery
  fs.writeFileSync(path.join(tempDir, "settings.json"), JSON.stringify(settings, null, 2));

  // Reset pipeline log file for this run
  const logPath = path.join(tempDir, "pipeline.log");
  if (fs.existsSync(logPath)) {
    try {
      fs.unlinkSync(logPath);
    } catch {}
  }

  const writeDebugLog = (chunk: any) => {
    try {
      fs.appendFileSync(jobDebugLogPath, chunk);
      fs.appendFileSync(rootDebugLogPath, chunk);
    } catch { /* ignore non-fatal file write errors */ }
  };

  const pipelinePath = path.join(root, "ai", "pipeline", "pipeline.py");
  const child = spawn("python", [
    pipelinePath,
    "--job-id",
    jobId,
    "--settings",
    JSON.stringify(settings)
  ], {
    cwd: root,
    env: {
      ...process.env,
      HF_HUB_DISABLE_SYMLINKS_WARNING: "1",
      HF_HUB_DOWNLOAD_TIMEOUT: "120",
      PYTHONUNBUFFERED: "1",
      PYTHONIOENCODING: "utf-8",
      PYTHONUTF8: "1"
    }
  });

  activeProcesses.set(jobId, child);

  // Update project status to processing as soon as pipeline starts
  try { writeProject(jobId, { status: "processing", settings }); } catch { /* non-fatal */ }

  child.stdout.on("data", (chunk) => {
    writeDebugLog(chunk);
    // Append to pipeline log
    try {
      fs.appendFileSync(logPath, chunk);
    } catch {}

    for (const line of chunk.toString().split(/\r?\n/).filter(Boolean)) {
      try {
        const event = JSON.parse(line);
        if (event.type === "error") {
          io.emit("pipeline:error", event);
        } else {
          io.emit("pipeline:event", event);
        }
      } catch {
        io.emit("pipeline:log", { jobId, message: line });
      }
    }
  });

  child.stderr.on("data", (chunk) => {
    writeDebugLog(chunk);
    try {
      fs.appendFileSync(logPath, chunk);
    } catch {}
    io.emit("pipeline:error", { jobId, message: chunk.toString() });
  });

  child.on("close", (code) => {
    activeProcesses.delete(jobId);
    io.emit("pipeline:exit", { jobId, code });

    // Update project.json status based on exit code
    try {
      if (code === 0) {
        // Count clips from clips.json if available
        const storageRoot = path.resolve(process.env.STORAGE_PATH ?? path.join(root, "storage"));
        const clipsJsonPath = path.join(storageRoot, "outputs", jobId, "clips.json");
        let clipCount = 0;
        if (fs.existsSync(clipsJsonPath)) {
          const clipsData = JSON.parse(fs.readFileSync(clipsJsonPath, "utf-8"));
          clipCount = Array.isArray(clipsData.clips) ? clipsData.clips.length : 0;
        }
        writeProject(jobId, { status: "complete", clipCount });
      } else {
        writeProject(jobId, { status: "failed" });
      }
    } catch { /* non-fatal */ }
  });

  return child;
}

export function cancelPipeline(jobId: string) {
  const child = activeProcesses.get(jobId);

  if (!child) {
    return false;
  }

  child.kill();
  activeProcesses.delete(jobId);
  io.emit("pipeline:cancelled", { jobId });
  return true;
}
