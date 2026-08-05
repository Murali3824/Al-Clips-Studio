import fs from "fs";
import path from "path";
import { activeProcesses } from "./python.service.js";

const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");

// ─── Types ────────────────────────────────────────────────────────────────────

export type ProjectStatus = "uploading" | "processing" | "complete" | "failed";

export interface ProjectData {
  jobId: string;
  name: string;
  originalFileName: string;
  createdAt: string;
  updatedAt: string;
  status: ProjectStatus;
  clipCount: number;
  storageBytes?: number;
  lastActiveStep?: string;
  settings?: Record<string, unknown>;
}

export interface ProjectSummary extends ProjectData {
  storageBytes: number;
  thumbnailUrl?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getDirSizeBytes(dir: string): number {
  if (!fs.existsSync(dir)) return 0;
  try {
    const stat = fs.statSync(dir);
    if (stat.isFile()) return stat.size;
    let total = 0;
    for (const child of fs.readdirSync(dir)) {
      total += getDirSizeBytes(path.join(dir, child));
    }
    return total;
  } catch {
    return 0;
  }
}

export function getProjectStorageBytes(jobId: string): number {
  return (
    getDirSizeBytes(path.join(storageRoot, "uploads", jobId)) +
    getDirSizeBytes(path.join(storageRoot, "outputs", jobId)) +
    getDirSizeBytes(path.join(storageRoot, "temp", jobId))
  );
}

/** Returns the canonical path to project.json — outputs dir preferred, falls back to uploads. */
function resolveProjectJsonPath(jobId: string): { read: string | null; write: string } {
  const outputsPath = path.join(storageRoot, "outputs", jobId, "project.json");
  const uploadsPath = path.join(storageRoot, "uploads", jobId, "project.json");

  // Prefer outputs dir (exists once processing has started)
  if (fs.existsSync(outputsPath)) return { read: outputsPath, write: outputsPath };
  // Fall back to uploads dir
  if (fs.existsSync(uploadsPath)) {
    // Migrate to outputs if outputs dir now exists
    const outputsDir = path.join(storageRoot, "outputs", jobId);
    if (fs.existsSync(outputsDir)) {
      return { read: uploadsPath, write: outputsPath };
    }
    return { read: uploadsPath, write: uploadsPath };
  }

  // Neither exists yet — decide write target based on which dir exists
  const outputsDir = path.join(storageRoot, "outputs", jobId);
  if (fs.existsSync(outputsDir)) return { read: null, write: outputsPath };
  return { read: null, write: uploadsPath };
}

// ─── CRUD ─────────────────────────────────────────────────────────────────────

export function readProject(jobId: string): ProjectData | null {
  const { read } = resolveProjectJsonPath(jobId);
  if (!read) return null;
  try {
    const data = JSON.parse(fs.readFileSync(read, "utf-8")) as ProjectData;
    if (!data.storageBytes || data.storageBytes <= 0) {
      const bytes = getProjectStorageBytes(jobId);
      if (bytes > 0) {
        data.storageBytes = bytes;
        try { fs.writeFileSync(read, JSON.stringify(data, null, 2)); } catch {}
      }
    }
    return data;
  } catch {
    return null;
  }
}

export function writeProject(
  jobId: string,
  data: Partial<Omit<ProjectData, "jobId">>
): ProjectData {
  const { read, write } = resolveProjectJsonPath(jobId);
  const existing: Partial<ProjectData> = read
    ? (() => { try { return JSON.parse(fs.readFileSync(read, "utf-8")); } catch { return {}; } })()
    : {};

  const resolvedStorageBytes = data.storageBytes ?? existing.storageBytes ?? getProjectStorageBytes(jobId);

  const merged: ProjectData = {
    jobId,
    name: data.name ?? existing.name ?? jobId,
    originalFileName: data.originalFileName ?? existing.originalFileName ?? "",
    createdAt: existing.createdAt ?? new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: data.status ?? existing.status ?? "uploading",
    clipCount: data.clipCount ?? existing.clipCount ?? 0,
    storageBytes: resolvedStorageBytes > 0 ? resolvedStorageBytes : undefined,
    lastActiveStep: data.lastActiveStep ?? existing.lastActiveStep,
    settings: data.settings ?? existing.settings,
  };

  // Ensure parent dir exists
  const parentDir = path.dirname(write);
  if (!fs.existsSync(parentDir)) fs.mkdirSync(parentDir, { recursive: true });

  fs.writeFileSync(write, JSON.stringify(merged, null, 2));

  // Clean up old location if we migrated
  if (read && read !== write && fs.existsSync(read)) {
    try { fs.unlinkSync(read); } catch { /* ignore */ }
  }

  return merged;
}

export function renameProject(jobId: string, name: string): ProjectData | null {
  const project = readProject(jobId);
  if (!project) return null;
  return writeProject(jobId, { name: name.trim() || project.name });
}

export function deleteProject(jobId: string): void {
  const dirs = [
    path.join(storageRoot, "uploads", jobId),
    path.join(storageRoot, "outputs", jobId),
    path.join(storageRoot, "temp", jobId),
  ];
  for (const dir of dirs) {
    if (fs.existsSync(dir)) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
}

function isOrphanFailedProject(project: ProjectData): boolean {
  if (project.status !== "failed") return false;
  const jobId = project.jobId;
  const uploadDir = path.join(storageRoot, "uploads", jobId);
  const outputClipsDir = path.join(storageRoot, "outputs", jobId, "clips");
  const tempDir = path.join(storageRoot, "temp", jobId);

  const hasSource = fs.existsSync(uploadDir) && fs.readdirSync(uploadDir).some((f) => !f.endsWith(".json"));
  const hasClips = fs.existsSync(outputClipsDir) && fs.readdirSync(outputClipsDir).length > 0;
  const hasTemp = fs.existsSync(tempDir) && fs.readdirSync(tempDir).length > 0;

  return !hasSource && !hasClips && !hasTemp;
}

export function listProjects(): ProjectSummary[] {
  const outputsRoot = path.join(storageRoot, "outputs");
  const uploadsRoot = path.join(storageRoot, "uploads");
  const projectMap = new Map<string, ProjectData>();

  // Scan outputs dir first (authoritative once processing has started)
  if (fs.existsSync(outputsRoot)) {
    for (const jobId of fs.readdirSync(outputsRoot)) {
      const jsonPath = path.join(outputsRoot, jobId, "project.json");
      if (!fs.existsSync(jsonPath)) continue;
      try {
        const data = JSON.parse(fs.readFileSync(jsonPath, "utf-8")) as ProjectData;
        projectMap.set(jobId, data);
      } catch { /* skip corrupt files */ }
    }
  }

  // Scan uploads dir for projects not yet moved to outputs (still uploading)
  if (fs.existsSync(uploadsRoot)) {
    for (const jobId of fs.readdirSync(uploadsRoot)) {
      if (projectMap.has(jobId)) continue;
      const jsonPath = path.join(uploadsRoot, jobId, "project.json");
      if (!fs.existsSync(jsonPath)) continue;
      try {
        const data = JSON.parse(fs.readFileSync(jsonPath, "utf-8")) as ProjectData;
        projectMap.set(jobId, data);
      } catch { /* skip corrupt files */ }
    }
  }

  return Array.from(projectMap.values())
    .filter((project) => {
      if (isOrphanFailedProject(project)) {
        deleteProject(project.jobId);
        return false;
      }
      return true;
    })
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .map((project) => {
      // Ensure status is accurately reported as 'processing' if python process is running
      const isActivelyProcessing = activeProcesses.has(project.jobId);
      const effectiveStatus = isActivelyProcessing ? "processing" : project.status;

      // Resolve first available thumbnail URL
      const thumbDir = path.join(storageRoot, "outputs", project.jobId, "thumbnails");
      let thumbnailUrl: string | undefined;
      if (fs.existsSync(thumbDir)) {
        const thumbFiles = fs.readdirSync(thumbDir).filter((f) => f.endsWith(".png"));
        if (thumbFiles.length > 0) {
          const clipId = thumbFiles[0].replace(".png", "");
          thumbnailUrl = `/api/results/${project.jobId}/thumbnails/${clipId}`;
        }
      }
      return {
        ...project,
        status: effectiveStatus,
        storageBytes: getProjectStorageBytes(project.jobId),
        thumbnailUrl,
      };
    });
}
