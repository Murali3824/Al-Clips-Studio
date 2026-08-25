import fs from "fs";
import path from "path";

const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");

export function ensureJobUploadDir(jobId: string) {
  const uploadRoot = path.resolve(storageRoot, "uploads");
  const jobDir = path.resolve(uploadRoot, jobId);

  if (!jobDir.startsWith(uploadRoot)) {
    throw new Error("Invalid upload path.");
  }

  fs.mkdirSync(jobDir, { recursive: true });
  return jobDir;
}
