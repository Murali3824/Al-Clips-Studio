import { create } from "zustand";
import { UploadResponse } from "../types/upload";

type UploadState = {
  error: string | null;
  file: { name: string; size: number } | File | null;
  job: UploadResponse | null;
  previewUrl: string | null;
  progress: number;
  setError: (error: string | null) => void;
  setFile: (file: { name: string; size: number } | File | null, previewUrl?: string | null) => void;
  setJob: (job: UploadResponse | null) => void;
  setProgress: (progress: number) => void;
};

export const useUploadStore = create<UploadState>((set) => ({
  error: null,
  file: null,
  job: null,
  previewUrl: null,
  progress: 0,
  setError: (error) => set({ error }),
  setFile: (file, previewUrl) => set({ file, previewUrl: previewUrl ?? null }),
  setJob: (job) => set({ job }),
  setProgress: (progress) => set({ progress })
}));
