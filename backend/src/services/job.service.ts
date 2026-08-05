import { randomUUID } from "crypto";

export type Job = {
  jobId: string;
  createdAt: string;
};

export function createJob(): Job {
  return {
    jobId: randomUUID(),
    createdAt: new Date().toISOString()
  };
}
