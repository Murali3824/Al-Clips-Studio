export type ProjectStatus = "uploading" | "processing" | "complete" | "failed";

export interface Project {
  jobId: string;
  name: string;
  originalFileName: string;
  createdAt: string;
  updatedAt: string;
  status: ProjectStatus;
  clipCount: number;
  storageBytes: number;
  thumbnailUrl?: string;
  lastActiveStep?: string;
  settings?: Record<string, unknown>;
}
