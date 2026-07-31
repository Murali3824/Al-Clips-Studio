import { create } from "zustand";
import { ClipResult } from "../types/results";

type EditorTab = "general" | "captions" | "hook" | "layout" | "music" | "meme" | "export";

type ResultsState = {
  clips: ClipResult[];
  selectedClipId: string | null;
  selectedClipIds: string[];
  editorOpen: boolean;
  editorTab: EditorTab;
  saving: boolean;
  clipEdits: Record<string, Partial<ClipResult>>;
  renderingClips: Record<string, { stage: string; progress: number }>;
  setClips: (clips: ClipResult[]) => void;
  setSelectedClipId: (clipId: string | null) => void;
  toggleClip: (clipId: string) => void;
  updateClipTrim: (clipId: string, trimStart: number, trimEnd: number) => void;
  openEditor: () => void;
  closeEditor: () => void;
  setEditorTab: (tab: EditorTab) => void;
  setSaving: (saving: boolean) => void;
  updateClipEdit: (clipId: string, edits: Partial<ClipResult>) => void;
  applyEditsToClip: (clipId: string) => void;
  getEffectiveClip: (clipId: string) => ClipResult | null;
  setRenderingClip: (clipId: string, stage: string | null, progress: number | null) => void;
};

export const useResultsStore = create<ResultsState>((set, get) => ({
  clips: [],
  selectedClipId: null,
  selectedClipIds: [],
  editorOpen: false,
  editorTab: "general",
  saving: false,
  clipEdits: {},
  renderingClips: {},
  setClips: (clips) => {
    const validSelected = clips[0]?.id ?? null;
    set({
      clips,
      selectedClipId: validSelected,
      selectedClipIds: clips.map((clip) => clip.id)
    });
  },
  setSelectedClipId: (selectedClipId) => {
    set({ selectedClipId });
  },
  toggleClip: (clipId) =>
    set((state) => ({
      selectedClipIds: state.selectedClipIds.includes(clipId)
        ? state.selectedClipIds.filter((id) => id !== clipId)
        : [...state.selectedClipIds, clipId]
    })),
  updateClipTrim: (clipId, trimStart, trimEnd) =>
    set((state) => ({
      clips: state.clips.map((clip) =>
        clip.id === clipId ? { ...clip, trimStart, trimEnd } : clip
      )
    })),
  openEditor: () => set({ editorOpen: true }),
  closeEditor: () => set({ editorOpen: false }),
  setEditorTab: (editorTab) => set({ editorTab }),
  setSaving: (saving) => set({ saving }),
  updateClipEdit: (clipId, edits) =>
    set((state) => ({
      clipEdits: {
        ...state.clipEdits,
        [clipId]: { ...(state.clipEdits[clipId] || {}), ...edits }
      }
    })),
  applyEditsToClip: (clipId) =>
    set((state) => {
      const edits = state.clipEdits[clipId];
      if (!edits) return state;
      return {
        clips: state.clips.map((clip) =>
          clip.id === clipId ? { ...clip, ...edits } : clip
        ),
        clipEdits: {
          ...state.clipEdits,
          [clipId]: {}
        }
      };
    }),
  getEffectiveClip: (clipId) => {
    const state = get();
    const clip = state.clips.find((c) => c.id === clipId);
    if (!clip) return null;
    const edits = state.clipEdits[clipId] || {};
    return { ...clip, ...edits };
  },
  setRenderingClip: (clipId, stage, progress) =>
    set((state) => {
      if (stage === null) {
        const next = { ...state.renderingClips };
        delete next[clipId];
        return { renderingClips: next };
      }
      return {
        renderingClips: {
          ...state.renderingClips,
          [clipId]: { stage, progress: progress ?? 0 }
        }
      };
    })
}));
