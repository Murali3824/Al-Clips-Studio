import fs from "fs";
import { getUserSettingsPath } from "../utils/configPaths.js";

const defaultSettings = {
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
  autoHookFontSize: 90,
  autoHookColor: "#ffffff",
  autoHookBgColor: "#000000",
  autoHookPosition: "top-center",
  autoHookDuration: 5,
  autoHookPadding: 12,
  autoHookRadius: 8,
  autoHookFadeIn: 300,
  autoHookFadeOut: 500,
};

// Map legacy hook2*/hook1* keys to new autoHook* keys for backward compatibility
function migrateSettings(raw: Record<string, unknown>): Record<string, unknown> {
  const migrated = { ...raw };
  const keyMap: Record<string, string> = {
    hook2Enabled: "autoHook",
    hook2Font: "autoHookFont",
    hook2FontSize: "autoHookFontSize",
    hook2Color: "autoHookColor",
    hook2BgColor: "autoHookBgColor",
    hook2Position: "autoHookPosition",
    hook2Duration: "autoHookDuration",
    hook2Padding: "autoHookPadding",
    hook2Radius: "autoHookRadius",
    hook2FadeIn: "autoHookFadeIn",
    hook2FadeOut: "autoHookFadeOut",
  };

  for (const [oldKey, newKey] of Object.entries(keyMap)) {
    if (oldKey in migrated && !(newKey in migrated)) {
      migrated[newKey] = migrated[oldKey];
    }
    delete migrated[oldKey];
  }

  // Remove all hook1* legacy keys
  for (const key of Object.keys(migrated)) {
    if (key.startsWith("hook1")) {
      delete migrated[key];
    }
  }

  return migrated;
}

export function readSettings() {
  const settingsPath = getUserSettingsPath();

  if (!fs.existsSync(settingsPath)) {
    return writeSettings(defaultSettings);
  }

  const raw = JSON.parse(fs.readFileSync(settingsPath, "utf-8"));
  return {
    ...defaultSettings,
    ...migrateSettings(raw)
  };
}

export function writeSettings(settings: Record<string, unknown>) {
  const nextSettings = {
    ...defaultSettings,
    ...settings
  };

  fs.writeFileSync(getUserSettingsPath(), JSON.stringify(nextSettings, null, 2));
  return nextSettings;
}
