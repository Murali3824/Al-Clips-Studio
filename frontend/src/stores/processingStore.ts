import { create } from "zustand";
import { PipelineEvent, PipelineStatus, StageProgress } from "../types/processing";

// 20 Canonical Stages matching Python pipeline and Backend API in exact execution order
const stageLabels: Record<string, string> = {
  stage_01_audio: "Audio extraction",
  stage_02_vad: "Voice activity detection",
  stage_03_transcription: "Transcription",
  stage_03_speaker_diarization: "Speaker diarization",
  stage_04_highlights: "Highlight detection",
  stage_05_scene_detection: "Scene detection",
  stage_06_face_detection: "Face detection",
  stage_07_face_tracking: "Face tracking",
  stage_07_subject_identity: "Subject identity continuity",
  stage_08_shot_selection: "Editorial shot selection",
  stage_08b_anchor_stream: "Per-frame anchor stream",
  stage_08c_camera_operator: "Spring-damped camera operator",
  stage_08d_transition_planner: "Smooth editorial transitions",
  stage_09_cut_crop: "Video cut and crop",
  stage_10_captions: "Caption generation",
  stage_11_metadata: "Metadata generation",
  stage_12_export: "Export preparation",
  stage_15_translation: "Translation",
  stage_14_music: "Background music",
  stage_13_thumbnails: "Thumbnail generation"
};

const initialStages: StageProgress[] = Object.entries(stageLabels).map(([id, label]) => ({
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

      const nextStatus: PipelineStatus =
        event.stage === "pipeline" && event.status === "complete"
          ? "complete"
          : event.stage === "pipeline" && (event.status === "started" || event.status === "running")
            ? "running"
            : event.status === "failed"
              ? "failed"
              : state.status;

      const targetIndex = state.stages.findIndex((s) => s.id === event.stage);

      let updatedStages = state.stages;
      if (targetIndex !== -1) {
        updatedStages = state.stages.map((stage, idx) => {
          // Finite State Machine Rule 1: Prerequisite stages prior to targetIndex MUST be completed
          if (idx < targetIndex) {
            return {
              ...stage,
              status: "complete" as const,
              percent: 100
            };
          }

          // Target stage event update
          if (idx === targetIndex) {
            if (event.status === "complete") {
              return {
                ...stage,
                status: "complete" as const,
                percent: 100
              };
            }
            if (event.status === "started" || event.status === "running") {
              return {
                ...stage,
                status: "running" as const,
                percent: Math.max(stage.percent, event.percent ?? 0)
              };
            }
            if (event.status === "failed") {
              return {
                ...stage,
                status: "failed" as const,
                percent: stage.percent
              };
            }
          }

          // Downstream stages remain pending unless already completed
          return stage;
        });
      }

      // Compute overall monotonic pipeline percentage
      const completedCount = updatedStages.filter((s) => s.status === "complete").length;
      const calculatedPercent = Math.floor((completedCount / updatedStages.length) * 100);
      const newPercent = Math.max(state.percent, event.percent ?? calculatedPercent);

      return {
        activeJobId: event.jobId || state.activeJobId,
        logs: [...state.logs.slice(-80), `${newPercent}% ${event.message}`],
        percent: newPercent,
        status: nextStatus,
        stages: updatedStages
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
            status: (matching.status === "error" ? "failed" : matching.status) as StageProgress["status"]
          };
        }
        return stage;
      });

      // Enforce state machine sequential integrity on restored state
      const firstIncompleteIdx = nextStages.findIndex(
        (s) => s.status === "running" || s.status === "pending" || s.status === "failed"
      );

      const guardedStages = nextStages.map((stage, idx) => {
        if (firstIncompleteIdx !== -1 && idx < firstIncompleteIdx) {
          return { ...stage, status: "complete" as const, percent: 100 };
        }
        return stage;
      });

      return {
        percent,
        stages: guardedStages,
        logs
      };
    });
  }
}));
