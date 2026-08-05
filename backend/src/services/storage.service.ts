import fs from "fs";
import path from "path";
import { listProjects, readProject, writeProject, deleteProject } from "./project.service.js";

const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");

export type CleanupCategory = "temp" | "clips" | "uploads" | "everything";

export interface StorageBreakdown {
  totalBytes: number;
  uploadedVideosBytes: number;
  generatedClipsBytes: number;
  tempFilesBytes: number;
  uploadedVideosCount: number;
  generatedClipsCount: number;
  tempFilesCount: number;
}

export interface CleanupItemResult {
  jobId: string;
  name: string;
  status: string;
}

export interface CleanupResult {
  category: CleanupCategory;
  deleted: CleanupItemResult[];
  skipped: CleanupItemResult[];
  freedBytes: number;
  breakdown: StorageBreakdown;
}

// ─── File System Helpers ──────────────────────────────────────────────────────

function getPathSizeBytes(targetPath: string): number {
  if (!fs.existsSync(targetPath)) return 0;
  try {
    const stat = fs.statSync(targetPath);
    if (stat.isFile()) return stat.size;
    let total = 0;
    for (const child of fs.readdirSync(targetPath)) {
      total += getPathSizeBytes(path.join(targetPath, child));
    }
    return total;
  } catch {
    return 0;
  }
}

function countFilesInDir(targetPath: string): number {
  if (!fs.existsSync(targetPath)) return 0;
  try {
    const stat = fs.statSync(targetPath);
    if (stat.isFile()) return 1;
    let count = 0;
    for (const child of fs.readdirSync(targetPath)) {
      count += countFilesInDir(path.join(targetPath, child));
    }
    return count;
  } catch {
    return 0;
  }
}

function removeDirOrFile(targetPath: string): number {
  if (!fs.existsSync(targetPath)) return 0;
  const size = getPathSizeBytes(targetPath);
  try {
    fs.rmSync(targetPath, { recursive: true, force: true });
  } catch (err) {
    console.error(`Failed to remove ${targetPath}:`, err);
  }
  return size;
}

// ─── Active Job Safety Check ──────────────────────────────────────────────────

const ACTIVE_STATUSES = new Set(["uploading", "processing", "queued", "rendering", "generating"]);

export function isActiveProjectStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status.toLowerCase());
}

// ─── Check Source Video Existence ─────────────────────────────────────────────

export function checkSourceVideoExists(jobId: string): boolean {
  const uploadDir = path.join(storageRoot, "uploads", jobId);
  if (!fs.existsSync(uploadDir)) return false;
  try {
    const files = fs.readdirSync(uploadDir);
    // Source video is any non-json file in uploads directory
    return files.some((f) => !f.endsWith(".json"));
  } catch {
    return false;
  }
}

// ─── Storage Breakdown ────────────────────────────────────────────────────────

export function getStorageBreakdown(): StorageBreakdown {
  const uploadsDir = path.join(storageRoot, "uploads");
  const outputsDir = path.join(storageRoot, "outputs");
  const tempDir = path.join(storageRoot, "temp");

  let uploadedVideosBytes = 0;
  let uploadedVideosCount = 0;

  let generatedClipsBytes = 0;
  let generatedClipsCount = 0;

  let tempFilesBytes = 0;
  let tempFilesCount = 0;

  // 1. Uploaded Source Videos
  if (fs.existsSync(uploadsDir)) {
    for (const jobId of fs.readdirSync(uploadsDir)) {
      const jobUploadPath = path.join(uploadsDir, jobId);
      if (!fs.statSync(jobUploadPath).isDirectory()) continue;
      for (const file of fs.readdirSync(jobUploadPath)) {
        if (!file.endsWith(".json")) {
          const filePath = path.join(jobUploadPath, file);
          uploadedVideosBytes += getPathSizeBytes(filePath);
          uploadedVideosCount += 1;
        }
      }
    }
  }

  // 2. Generated Clips & Rendered Outputs (clips, thumbnails, translations, exports)
  if (fs.existsSync(outputsDir)) {
    for (const jobId of fs.readdirSync(outputsDir)) {
      const jobOutputPath = path.join(outputsDir, jobId);
      if (!fs.statSync(jobOutputPath).isDirectory()) continue;

      const subdirs = ["clips", "thumbnails", "translations", "music_clips", "captioned_clips"];
      for (const sub of subdirs) {
        const subPath = path.join(jobOutputPath, sub);
        if (fs.existsSync(subPath)) {
          generatedClipsBytes += getPathSizeBytes(subPath);
          generatedClipsCount += countFilesInDir(subPath);
        }
      }
      const zipPath = path.join(jobOutputPath, "export.zip");
      if (fs.existsSync(zipPath)) {
        generatedClipsBytes += getPathSizeBytes(zipPath);
        generatedClipsCount += 1;
      }
    }
  }

  // 3. Temporary & Intermediate Files
  if (fs.existsSync(tempDir)) {
    tempFilesBytes += getPathSizeBytes(tempDir);
    tempFilesCount += countFilesInDir(tempDir);
  }

  const totalBytes = uploadedVideosBytes + generatedClipsBytes + tempFilesBytes;

  return {
    totalBytes,
    uploadedVideosBytes,
    generatedClipsBytes,
    tempFilesBytes,
    uploadedVideosCount,
    generatedClipsCount,
    tempFilesCount,
  };
}

// ─── Storage Cleanup ──────────────────────────────────────────────────────────

export function cleanupStorage(category: CleanupCategory): CleanupResult {
  const initialBreakdown = getStorageBreakdown();
  const allProjects = listProjects();

  const deleted: CleanupItemResult[] = [];
  const skipped: CleanupItemResult[] = [];

  for (const project of allProjects) {
    const { jobId, name, status } = project;

    // RULE: NEVER touch active projects! Always skip!
    if (isActiveProjectStatus(status)) {
      skipped.push({ jobId, name, status });
      continue;
    }

    let projectCleaned = false;

    if (category === "everything") {
      // Clear Everything removes ALL storage AND metadata for eligible non-active projects
      deleteProject(jobId);
      projectCleaned = true;
    } else {
      // 1. Delete Temporary Files
      if (category === "temp") {
        const tempJobPath = path.join(storageRoot, "temp", jobId);
        if (fs.existsSync(tempJobPath)) {
          removeDirOrFile(tempJobPath);
          projectCleaned = true;
        }
      }

      // 2. Delete Generated Clips
      if (category === "clips") {
        const outputJobPath = path.join(storageRoot, "outputs", jobId);
        if (fs.existsSync(outputJobPath)) {
          const itemsToRemove = ["clips", "thumbnails", "translations", "music_clips", "captioned_clips", "export.zip"];
          for (const item of itemsToRemove) {
            const target = path.join(outputJobPath, item);
            if (fs.existsSync(target)) {
              removeDirOrFile(target);
              projectCleaned = true;
            }
          }
          writeProject(jobId, { clipCount: 0 });
        }
      }

      // 3. Delete Uploaded Videos
      if (category === "uploads") {
        const uploadJobPath = path.join(storageRoot, "uploads", jobId);
        if (fs.existsSync(uploadJobPath)) {
          for (const file of fs.readdirSync(uploadJobPath)) {
            if (!file.endsWith(".json")) {
              const videoPath = path.join(uploadJobPath, file);
              removeDirOrFile(videoPath);
              projectCleaned = true;
            }
          }
        }
      }

      // Check if a failed/cancelled project now has no remaining source video, clips, or temp files
      const hasSource = checkSourceVideoExists(jobId);
      const outputClipsDir = path.join(storageRoot, "outputs", jobId, "clips");
      const hasClips = fs.existsSync(outputClipsDir) && fs.readdirSync(outputClipsDir).length > 0;
      const isFailedOrCancelled = status.toLowerCase() === "failed" || status.toLowerCase() === "cancelled";

      if (isFailedOrCancelled && !hasSource && !hasClips) {
        deleteProject(jobId);
        projectCleaned = true;
      }
    }

    if (projectCleaned) {
      deleted.push({ jobId, name, status });
    }
  }

  // Also clean unattached global temp files if cleaning temp or everything
  if (category === "temp" || category === "everything") {
    const tempDir = path.join(storageRoot, "temp");
    if (fs.existsSync(tempDir)) {
      for (const entry of fs.readdirSync(tempDir)) {
        const entryPath = path.join(tempDir, entry);
        if (isActiveProjectStatus(entry)) continue;
        const projectInfo = allProjects.find((p) => p.jobId === entry);
        if (projectInfo && isActiveProjectStatus(projectInfo.status)) {
          continue;
        }
        removeDirOrFile(entryPath);
      }
    }
  }

  const newBreakdown = getStorageBreakdown();
  const freedBytes = Math.max(0, initialBreakdown.totalBytes - newBreakdown.totalBytes);

  return {
    category,
    deleted,
    skipped,
    freedBytes,
    breakdown: newBreakdown,
  };
}
