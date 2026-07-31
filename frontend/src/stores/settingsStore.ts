import { create } from "zustand";
import { ProcessingSettings } from "../types/settings";

const defaultSettings: ProcessingSettings = {
  clipGenerationMode: "auto",
  coverageMode: "best",
  preferredDuration: "auto",
  clipCount: 5,
  minClipDuration: 20,
  maxClipDuration: 30,
  whisperModel: "medium",
  speakerDiarization: false,
  backgroundMusic: false,
  musicVolume: 20,
  thumbnailGeneration: true,
  silenceRemoval: true,
  translationLanguages: [],
  captionStyle: "classic-white",
  captionDisplayMode: "phrase",
  captionFontSize: 72,
  captionPosition: "bottom",
  layoutMode: "auto",
  highlightColorMode: "single",
  highlightColor: "yellow",
  // Modular Caption Engine Defaults
  captionFontPreset: "bold",
  captionContainerType: "none",
  captionAnimationType: "none",
  captionFontFamily: "Arial Black",
  captionFontWeight: "bold",
  captionLetterSpacing: 0,
  captionLineHeight: 1.2,
  captionTextColor: "#ffffff",
  captionHighlightColor: "#ffff00",
  captionBgColor: "#000000",
  captionOutlineColor: "#000000",
  captionShadowColor: "#000000",
  captionBorderRadius: 8,
  captionPadding: 12,
  captionOpacity: 100,
  captionOutlineSize: 3,
  captionShadowSize: 2,
  captionCustomMarginV: 170,
  // Single Universal Auto Hook Defaults
  autoHook: true,
  autoHookText: "",
  autoHookFont: "Arial Black",
  autoHookFontSize: 120,
  autoHookColor: "#ffffff",
  autoHookBgColor: "#000000",
  autoHookPosition: "top-center",
  autoHookDuration: 5,
  autoHookDurationMode: "custom",
  autoHookPadding: 12,
  autoHookRadius: 8,
  autoHookFadeIn: 300,
  autoHookFadeOut: 500,
};

type SettingsState = {
  settings: ProcessingSettings;
  setSettings: (settings: ProcessingSettings) => void;
  updateSetting: <Key extends keyof ProcessingSettings>(
    key: Key,
    value: ProcessingSettings[Key]
  ) => void;
};

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: defaultSettings,
  setSettings: (settings) => set({ settings: { ...defaultSettings, ...settings } }),
  updateSetting: (key, value) =>
    set((state) => ({ settings: { ...state.settings, [key]: value } })),
}));
