export type PipelineStatus =
  | "idle"
  | "running"
  | "complete"
  | "failed"
  | "cancelled";

export type StageStatus = "pending" | "running" | "complete" | "skipped" | "failed";

export type PipelineEvent = {
  type: "progress";
  jobId: string;
  stage: string;
  status: StageStatus | "started";
  percent: number;
  message: string;
};

export type StageProgress = {
  id: string;
  label: string;
  percent: number;
  status: StageStatus;
};
