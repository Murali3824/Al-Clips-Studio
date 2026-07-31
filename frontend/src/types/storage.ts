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
