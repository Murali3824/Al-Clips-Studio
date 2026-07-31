import { create } from "zustand";
import { PipelineEvent, PipelineStatus, StageProgress } from "../types/processing";

const stageLabels: Record<string, string> = {
  stage_01_audio: "Audio extraction",
  stage_02_vad: "Voice activity detection",
  stage_03_transcription: "Transcription",
  stage_03_speaker_diarization: "Speaker diarization",
  stage_04_highlights: "Highlight detection",
  stage_05_scene_detection: "Scene detection",
  stage_06_face_detection: "Face detection",
  stage_07_face_tracking: "Face tracking",
  stage_08_smooth_crop: "Smooth crop",
  stage_09_cut_crop: "Video cut and crop",
  stage_10_captions: "Caption generation",
  stage_11_metadata: "Metadata generation",
  stage_12_export: "Export preparation",
  stage_15_translation: "Translation",
  stage_14_music: "Background music",
  stage_13_thumbnails: "Thumbnail generation"
};

const initialStages = Object.entries(stageLabels).map(([id, label]) => ({
  id,
  label,
  percent: 0,
  status: "pending" as const
}));

type ProcessingState = {
  activeJobId: string | null;
  logs: string[];
  percent: number;
  stages: StageProgress[];
  status: PipelineStatus;
  addLog: (message: string) => void;
  applyEvent: (event: PipelineEvent) => void;
  resetProcessing: (jobId: string) => void;
  setStatus: (status: PipelineStatus) => void;
  clearProcessing: () => void;
  initProcessing: (jobId: string, status: PipelineStatus) => void;
  restorePipelineProgress: (percent: number, stages: Array<{ id: string; percent: number; status: string }>, logs: string[]) => void;
};

export const useProcessingStore = create<ProcessingState>((set) => ({
  activeJobId: null,
  logs: [],
  percent: 0,
  stages: initialStages,
  status: "idle",
  addLog: (message) =>
    set((state) => ({ logs: [...state.logs.slice(-80), message] })),
  applyEvent: (event) =>
    set((state) => {
      if (state.activeJobId && event.jobId && state.activeJobId !== event.jobId) {
        return state;
      }
      const nextStatus =
        event.stage === "pipeline" && event.status === "complete"
          ? "complete"
          : event.stage === "pipeline" && event.status === "started"
            ? "running"
            : state.status;

      return {
        activeJobId: event.jobId || state.activeJobId,
        logs: [...state.logs.slice(-80), `${event.percent}% ${event.message}`],
        percent: event.percent,
        status: nextStatus,
        stages: state.stages.map((stage) =>
          stage.id === event.stage
            ? {
                ...stage,
                percent: event.percent,
                status:
                  event.status === "started"
                    ? "running"
                    : (event.status as StageProgress["status"])
              }
            : stage
        )
      };
    }),
  resetProcessing: (jobId) => {
    set({
      activeJobId: jobId,
      logs: [],
      percent: 0,
      stages: initialStages,
      status: "running"
    });
  },
  setStatus: (status) => set({ status }),
  clearProcessing: () => {
    set({
      activeJobId: null,
      logs: [],
      percent: 0,
      stages: initialStages,
      status: "idle"
    });
  },
  initProcessing: (jobId, status) => {
    set({
      activeJobId: jobId,
      logs: [],
      percent: 0,
      stages: initialStages,
      status
    });
  },
  restorePipelineProgress: (percent, stages, logs) => {
    set((state) => {
      const nextStages = state.stages.map((stage) => {
        const matching = stages.find((s) => s.id === stage.id);
        if (matching) {
          return {
            ...stage,
            percent: matching.percent,
            status: matching.status as StageProgress["status"]
          };
        }
        return stage;
      });
      return {
        percent,
        stages: nextStages,
        logs
      };
    });
  }
}));
