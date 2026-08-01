import React from "react";
import { Slider } from "../Common/Slider";
import { Toggle } from "../Common/Toggle";
import { ColorPicker } from "../Common/ColorPicker";
import { Button } from "../Common/Button";

interface EditorLayoutProps {
  selectedClip: any;
  clipEdits: Record<string, any>;
  editorTab: any;
  setEditorTab: (tab: any) => void;
  updateClipEdit: (clipId: string, edits: any) => void;
  memes: any[];
  musicTracks: any[];
  hasMusicLibrary: boolean;
  settings: any;
  handleAssetUpload: (type: "memes", file: File) => Promise<void>;
  activeJobId: string | null;
  selectedClipIds: string[];
  exportSelected: () => void;
}

const FONT_PRESETS: Record<string, { fontFamily: string; fontWeight: "normal" | "bold"; letterSpacing: number; lineHeight: number }> = {
  "minimal": { fontFamily: "Helvetica", fontWeight: "normal", letterSpacing: 1, lineHeight: 1.2 },
  "clean-white": { fontFamily: "Arial", fontWeight: "bold", letterSpacing: 0, lineHeight: 1.2 },
  "bold": { fontFamily: "Arial Black", fontWeight: "bold", letterSpacing: 0, lineHeight: 1.2 },
  "modern": { fontFamily: "Trebuchet MS", fontWeight: "bold", letterSpacing: 0.5, lineHeight: 1.3 },
  "rounded": { fontFamily: "Arial Rounded MT Bold", fontWeight: "bold", letterSpacing: 0, lineHeight: 1.2 },
  "heavy": { fontFamily: "Impact", fontWeight: "bold", letterSpacing: 0.5, lineHeight: 1.1 },
  "condensed": { fontFamily: "Arial Narrow", fontWeight: "bold", letterSpacing: -0.5, lineHeight: 1.1 },
  "elegant": { fontFamily: "Georgia", fontWeight: "bold", letterSpacing: 0.5, lineHeight: 1.4 },
  "classic": { fontFamily: "Times New Roman", fontWeight: "normal", letterSpacing: 0, lineHeight: 1.2 },
  "creator": { fontFamily: "Impact", fontWeight: "bold", letterSpacing: 1.0, lineHeight: 1.1 },
};

export const EditorLayout: React.FC<EditorLayoutProps> = ({
  selectedClip,
  clipEdits,
  editorTab,
  setEditorTab,
  updateClipEdit,
  memes,
  musicTracks,
  hasMusicLibrary,
  settings,
  handleAssetUpload,
  activeJobId,
  selectedClipIds,
  exportSelected,
}) => {
  if (!selectedClip) return null;

  const ec = { ...selectedClip, ...(clipEdits[selectedClip.id] || {}) };
  const setEdit = (key: string, value: any) => {
    updateClipEdit(selectedClip.id, { [key]: value });
  };

  const applyPreset = (presetId: string) => {
    if (presetId === "custom") {
      updateClipEdit(selectedClip.id, { captionStyle: "custom" });
      return;
    }
    const presetsDefs: Record<string, any> = {
      "bold": {
        captionFontPreset: "bold", captionContainerType: "none", captionAnimationType: "pop",
        highlightColorMode: "single", captionHighlightColor: "#facc15", captionFontFamily: "Arial Black",
        captionFontWeight: "bold", captionLetterSpacing: 0, captionLineHeight: 1.2
      },
      "minimal": {
        captionFontPreset: "minimal", captionContainerType: "none", captionAnimationType: "fade",
        highlightColorMode: "single", captionHighlightColor: "#ffffff", captionFontFamily: "Helvetica",
        captionFontWeight: "normal", captionLetterSpacing: 1, captionLineHeight: 1.2
      },
      "outline": {
        captionFontPreset: "heavy", captionContainerType: "outline", captionAnimationType: "pop",
        highlightColorMode: "single", captionHighlightColor: "#f97316", captionFontFamily: "Impact",
        captionFontWeight: "bold", captionLetterSpacing: 0.5, captionLineHeight: 1.1
      },
      "boxed": {
        captionFontPreset: "clean-white", captionContainerType: "solid", captionAnimationType: "none",
        highlightColorMode: "single", captionHighlightColor: "#60a5fa", captionFontFamily: "Arial",
        captionFontWeight: "bold", captionLetterSpacing: 0, captionLineHeight: 1.2
      },
      "karaoke-bounce": {
        captionFontPreset: "bold", captionContainerType: "none", captionAnimationType: "bounce",
        highlightColorMode: "single", captionHighlightColor: "#60a5fa", captionFontFamily: "Arial Black",
        captionFontWeight: "bold", captionLetterSpacing: 0, captionLineHeight: 1.2
      },
      "clean-white": {
        captionFontPreset: "clean-white", captionContainerType: "none", captionAnimationType: "none",
        highlightColorMode: "none", captionHighlightColor: "#ffffff", captionFontFamily: "Arial",
        captionFontWeight: "bold", captionLetterSpacing: 0, captionLineHeight: 1.2
      },
      "creator": {
        captionFontPreset: "creator", captionContainerType: "outline", captionAnimationType: "elastic",
        highlightColorMode: "creator", captionHighlightColor: "#facc15", captionFontFamily: "Impact",
        captionFontWeight: "bold", captionLetterSpacing: 1.0, captionLineHeight: 1.1
      },
      "viral-shorts": {
        captionFontPreset: "heavy", captionContainerType: "shadow", captionAnimationType: "bounce",
        highlightColorMode: "single", captionHighlightColor: "#facc15", captionFontFamily: "Impact",
        captionFontWeight: "bold", captionLetterSpacing: 0.5, captionLineHeight: 1.1
      },
      "tiktok": {
        captionFontPreset: "bold", captionContainerType: "transparent-box", captionAnimationType: "pop",
        highlightColorMode: "single", captionHighlightColor: "#38bdf8", captionFontFamily: "Arial Black",
        captionFontWeight: "bold", captionLetterSpacing: 0, captionLineHeight: 1.2
      },
      "podcast": {
        captionFontPreset: "modern", captionContainerType: "border-only", captionAnimationType: "none",
        highlightColorMode: "single", captionHighlightColor: "#facc15", captionFontFamily: "Trebuchet MS",
        captionFontWeight: "bold", captionLetterSpacing: 0.5, captionLineHeight: 1.3
      }
    };

    const val = presetsDefs[presetId];
    if (val) {
      updateClipEdit(selectedClip.id, {
        captionStyle: presetId,
        ...val
      });
    }
  };

  const applyFontPreset = (preset: string) => {
    if (preset === "custom") {
      updateClipEdit(selectedClip.id, { captionFontPreset: "custom" });
      return;
    }
    const val = FONT_PRESETS[preset];
    if (val) {
      updateClipEdit(selectedClip.id, {
        captionFontPreset: preset,
        captionFontFamily: val.fontFamily,
        captionFontWeight: val.fontWeight,
        captionLetterSpacing: val.letterSpacing,
        captionLineHeight: val.lineHeight
      });
    }
  };

  const captionStylePresets = [
    { id: "bold", label: "Bold Pop" },
    { id: "minimal", label: "Minimalist" },
    { id: "outline", label: "Outline" },
    { id: "boxed", label: "Boxed" },
    { id: "karaoke-bounce", label: "Karaoke Bounce" },
    { id: "clean-white", label: "Clean White" },
    { id: "creator", label: "Creator Pro" },
    { id: "viral-shorts", label: "Viral Shorts" },
    { id: "tiktok", label: "TikTok Style" },
    { id: "podcast", label: "Podcast Style" },
  ];

  const fontPresets = [
    { id: "minimal", label: "Minimalist" },
    { id: "clean-white", label: "Clean White" },
    { id: "bold", label: "Bold & Heavy" },
    { id: "modern", label: "Modern" },
    { id: "rounded", label: "Rounded" },
    { id: "heavy", label: "Heavy Impact" },
    { id: "condensed", label: "Condensed" },
    { id: "elegant", label: "Elegant Georgia" },
    { id: "classic", label: "Classic Serif" },
    { id: "creator", label: "Creator Style" },
    { id: "custom", label: "Custom Style 🎛️" }
  ];

  const containerTypes = [
    { id: "none", label: "No Background" },
    { id: "solid", label: "Solid Box" },
    { id: "transparent-box", label: "Transparent Background" },
    { id: "outline", label: "High-Contrast Outline" },
    { id: "shadow", label: "Clean Shadow" },
    { id: "glow", label: "Ambient Glow" },
    { id: "border-only", label: "Border Outline Only" },
    { id: "gradient", label: "Gradient Background" }
  ];

  const animations = [
    { id: "none", label: "None" },
    { id: "fade", label: "Smooth Fade" },
    { id: "pop", label: "Pop Zoom" },
    { id: "bounce", label: "Karaoke Bounce" },
    { id: "scale", label: "Scale Up" },
    { id: "zoom", label: "Zoom In" },
    { id: "elastic", label: "Elastic Spring" }
  ];

  const highlightModes = [
    { id: "none", label: "No Highlight" },
    { id: "single", label: "Single Color" },
    { id: "multi", label: "Color Rotation" },
    { id: "creator", label: "Creator Highlight" }
  ];

  const tabs = ["general", "captions", "hook", "layout", "music", "meme", "export"] as const;

  return (
    <div className="bg-white">
      {/* Tab Navigation — underline style */}
      <div className="flex gap-0 overflow-x-auto border-b border-gray-100 px-6 select-none">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            className={`flex-shrink-0 px-4 py-3 text-sm font-medium capitalize transition-colors relative ${
              editorTab === tab
                ? "text-gray-950"
                : "text-gray-400 hover:text-gray-700"
            }`}
            onClick={() => setEditorTab(tab)}
          >
            {tab === "meme" ? "Meme" : tab}
            {editorTab === tab && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gray-950 rounded-full" />
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="p-6 space-y-5">
        {/* ── 1. General ── */}
        {editorTab === "general" && (
          <div className="space-y-4 animate-fade-in">
            <div className="space-y-1.5">
              <label className="field-label">Title</label>
              <input
                type="text"
                value={ec.title ?? ""}
                onChange={(e) => setEdit("title", e.target.value)}
                className="input-field"
              />
            </div>
            <div className="space-y-1.5">
              <label className="field-label">Description</label>
              <textarea
                value={ec.description ?? ""}
                onChange={(e) => setEdit("description", e.target.value)}
                rows={3}
                className="input-field resize-none"
              />
            </div>
            <div className="space-y-1.5">
              <label className="field-label">Tags (comma separated)</label>
              <input
                type="text"
                value={(ec.tags ?? []).join(", ")}
                onChange={(e) =>
                  setEdit(
                    "tags",
                    e.target.value
                      .split(",")
                      .map((t) => t.trim())
                      .filter(Boolean)
                  )
                }
                className="input-field"
              />
            </div>
            <div className="space-y-1.5">
              <label className="field-label">Target Social Platform</label>
              <select
                value={ec.platformRecommendation ?? ""}
                onChange={(e) => setEdit("platformRecommendation", e.target.value)}
                className="input-field"
              >
                <option value="">Auto (Optimized)</option>
                <option value="YouTube Shorts">YouTube Shorts</option>
                <option value="TikTok">TikTok</option>
                <option value="Instagram Reels">Instagram Reels</option>
                <option value="X / Twitter">X / Twitter</option>
              </select>
            </div>
          </div>
        )}

        {/* ── 2. Captions ── */}
        {editorTab === "captions" && (
          <div className="space-y-5 animate-fade-in max-h-[550px] overflow-y-auto pr-1">
            {/* Caption Style Preset */}
            <div>
              <label className="field-label mb-2">Caption Style Preset</label>
              <select
                value={ec.captionStyle ?? settings.captionStyle ?? "classic-white"}
                onChange={(e) => applyPreset(e.target.value)}
                className="input-field"
              >
                {captionStylePresets.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.label}</option>
                ))}
                <option value="custom">Custom Style 🎛️</option>
              </select>
            </div>

            {/* Font Style Typography Presets */}
            <div>
              <label className="field-label mb-2">Typography Preset</label>
              <select
                value={ec.captionFontPreset ?? settings.captionFontPreset ?? "bold"}
                onChange={(e) => applyFontPreset(e.target.value)}
                className="input-field"
              >
                {fontPresets.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.label}</option>
                ))}
              </select>
            </div>

            {/* Container Style */}
            <div>
              <label className="field-label mb-2">Background & Container</label>
              <select
                value={ec.captionContainerType ?? settings.captionContainerType ?? "none"}
                onChange={(e) => setEdit("captionContainerType", e.target.value)}
                className="input-field"
              >
                {containerTypes.map((type) => (
                  <option key={type.id} value={type.id}>{type.label}</option>
                ))}
              </select>
            </div>

            {/* Transition Animations */}
            <div>
              <label className="field-label mb-2">Caption Animation</label>
              <select
                value={ec.captionAnimationType ?? settings.captionAnimationType ?? "none"}
                onChange={(e) => setEdit("captionAnimationType", e.target.value)}
                className="input-field"
              >
                {animations.map((anim) => (
                  <option key={anim.id} value={anim.id}>{anim.label}</option>
                ))}
              </select>
            </div>

            {/* Highlight System */}
            <div>
              <label className="field-label mb-2">Highlighting Mode</label>
              <select
                value={ec.highlightColorMode ?? settings.highlightColorMode ?? "single"}
                onChange={(e) => setEdit("highlightColorMode", e.target.value)}
                className="input-field"
              >
                {highlightModes.map((mode) => (
                  <option key={mode.id} value={mode.id}>{mode.label}</option>
                ))}
              </select>
            </div>

            {/* Color Rotation Steps for Multi mode */}
            {(ec.highlightColorMode ?? settings.highlightColorMode ?? "single") === "multi" && (
              <div className="flex flex-col gap-3 bg-gray-50 p-4 rounded-xl border border-gray-200 animate-fade-in">
                <span className="field-label">Rotation Steps (4 Colors)</span>
                <div className="grid grid-cols-4 gap-2">
                  {(ec.captionMultiColors ?? settings.captionMultiColors ?? ["#ffff00", "#22c55e", "#ef4444", "#3b82f6"]).map((colorHex: string, idx: number) => {
                    const multiColors = ec.captionMultiColors ?? settings.captionMultiColors ?? ["#ffff00", "#22c55e", "#ef4444", "#3b82f6"];
                    return (
                      <div key={idx} className="flex flex-col items-center gap-1.5">
                        <span className="text-[10px] text-gray-500 font-bold">Step {idx + 1}</span>
                        <div className="relative">
                          <input
                            type="color"
                            value={colorHex}
                            onChange={(e) => {
                              const next = [...multiColors];
                              next[idx] = e.target.value;
                              setEdit("captionMultiColors", next);
                            }}
                            className="w-7 h-7 rounded-full border border-gray-200 cursor-pointer p-0 bg-transparent"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Position */}
            <div>
              <label className="field-label mb-2">Caption Position</label>
              <select
                value={ec.captionPosition ?? settings.captionPosition ?? "bottom"}
                onChange={(e) => setEdit("captionPosition", e.target.value)}
                className="input-field"
              >
                <option value="bottom">Bottom (Standard)</option>
                <option value="lower-third">Lower Third</option>
                <option value="center">Center Focus</option>
                <option value="top-center">Top Center</option>
                <option value="top">Top Margin</option>
                <option value="custom">Custom Position 🎛️-y</option>
              </select>
            </div>

            {(ec.captionPosition ?? settings.captionPosition ?? "bottom") === "custom" && (
              <Slider
                label="Custom vertical margin (bottom-up)"
                min={20}
                max={1500}
                value={ec.captionCustomMarginV ?? settings.captionCustomMarginV ?? 170}
                onChange={(val) => setEdit("captionCustomMarginV", val)}
                unit="px"
              />
            )}

            {/* Segmentation / Display Mode */}
            <div className="space-y-3">
              <label className="field-label">Caption Mode (Segmentation)</label>
              <div className="space-y-2">
                <label className="flex items-center gap-3 cursor-pointer select-none">
                  <input
                    type="radio"
                    name="captionMode"
                    checked={
                      (ec.captionDisplayMode ?? settings.captionDisplayMode ?? "phrase") !== "phrase" &&
                      (ec.captionDisplayMode ?? settings.captionDisplayMode ?? "phrase") !== "sentence"
                    }
                    onChange={() => setEdit("captionDisplayMode", "3-words")}
                    className="accent-gray-950"
                  />
                  <span className="text-sm text-gray-700">Word Count Mode</span>
                </label>

                {((ec.captionDisplayMode ?? settings.captionDisplayMode ?? "phrase") !== "phrase" &&
                  (ec.captionDisplayMode ?? settings.captionDisplayMode ?? "phrase") !== "sentence") && (() => {
                    const currentVal = ec.captionDisplayMode ?? settings.captionDisplayMode ?? "3-words";
                    let currentCount = 3;
                    if (currentVal === "word") {
                      currentCount = 1;
                    } else {
                      const match = currentVal.match(/^(\d+)-words?$/);
                      if (match) currentCount = parseInt(match[1], 10);
                    }
                    return (
                      <div className="pl-7 flex items-center gap-3 animate-fade-in">
                        <span className="text-xs text-gray-500 font-medium">Words per caption:</span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              const next = Math.max(1, currentCount - 1);
                              setEdit("captionDisplayMode", next === 1 ? "word" : `${next}-words`);
                            }}
                            className="h-6 w-6 rounded border border-gray-200 bg-white text-sm font-bold text-gray-700 hover:bg-gray-50 flex items-center justify-center"
                          >
                            −
                          </button>
                          <span className="font-mono text-sm text-gray-950 font-semibold w-6 text-center">
                            {currentCount}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              const next = Math.min(20, currentCount + 1);
                              setEdit("captionDisplayMode", `${next}-words`);
                            }}
                            className="h-6 w-6 rounded border border-gray-200 bg-white text-sm font-bold text-gray-700 hover:bg-gray-50 flex items-center justify-center"
                          >
                            +
                          </button>
                        </div>
                      </div>
                    );
                  })()}

                <label className="flex items-center gap-3 cursor-pointer select-none">
                  <input
                    type="radio"
                    name="captionMode"
                    checked={(ec.captionDisplayMode ?? settings.captionDisplayMode ?? "phrase") === "phrase"}
                    onChange={() => setEdit("captionDisplayMode", "phrase")}
                    className="accent-gray-950"
                  />
                  <span className="text-sm text-gray-700">Phrase Mode (Standard)</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer select-none">
                  <input
                    type="radio"
                    name="captionMode"
                    checked={(ec.captionDisplayMode ?? settings.captionDisplayMode ?? "phrase") === "sentence"}
                    onChange={() => setEdit("captionDisplayMode", "sentence")}
                    className="accent-gray-950"
                  />
                  <span className="text-sm text-gray-700">Full Sentence</span>
                </label>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* Advanced Granular Customization */}
            <details className="group border border-gray-200 rounded-xl bg-gray-50 overflow-hidden">
              <summary className="flex items-center justify-between p-4 font-semibold text-sm text-gray-900 cursor-pointer select-none hover:bg-gray-100 transition-colors">
                <span>Advanced Customization</span>
                <span className="transition-transform group-open:rotate-180">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </span>
              </summary>
              <div className="p-4 border-t border-gray-200 bg-white space-y-4 animate-fade-in">
                {/* Typography controls */}
                <div className="space-y-1.5">
                  <label className="field-label">Font Family</label>
                  <select
                    value={ec.captionFontFamily ?? settings.captionFontFamily ?? "Arial Black"}
                    onChange={(e) => { setEdit("captionFontFamily", e.target.value); setEdit("captionFontPreset", "custom"); }}
                    className="input-field"
                  >
                    {["Arial", "Arial Black", "Helvetica", "Impact", "Verdana", "Trebuchet MS", "Georgia", "Times New Roman", "Courier New"].map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="field-label">Weight</label>
                    <select
                      value={ec.captionFontWeight ?? settings.captionFontWeight ?? "bold"}
                      onChange={(e) => { setEdit("captionFontWeight", e.target.value); setEdit("captionFontPreset", "custom"); }}
                      className="input-field"
                    >
                      <option value="normal">Normal</option>
                      <option value="bold">Bold</option>
                    </select>
                  </div>
                  <Slider
                    label="Font Size"
                    min={24}
                    max={140}
                    value={ec.captionFontSize ?? settings.captionFontSize ?? 72}
                    onChange={(val) => setEdit("captionFontSize", val)}
                    unit="px"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <Slider
                    label="Letter Spacing"
                    min={-4}
                    max={15}
                    value={ec.captionLetterSpacing ?? settings.captionLetterSpacing ?? 0}
                    onChange={(val) => { setEdit("captionLetterSpacing", val); setEdit("captionFontPreset", "custom"); }}
                    unit="px"
                  />
                  <Slider
                    label="Line Height"
                    min={0.8}
                    max={2.2}
                    step={0.1}
                    value={ec.captionLineHeight ?? settings.captionLineHeight ?? 1.2}
                    onChange={(val) => { setEdit("captionLineHeight", val); setEdit("captionFontPreset", "custom"); }}
                    unit="x"
                  />
                </div>

                <hr className="border-gray-100" />

                {/* Box padding, border radius, opacity */}
                <div className="grid grid-cols-2 gap-3">
                  <Slider
                    label="Box Padding"
                    min={0}
                    max={40}
                    value={ec.captionPadding ?? settings.captionPadding ?? 12}
                    onChange={(val) => setEdit("captionPadding", val)}
                    unit="px"
                  />
                  <Slider
                    label="Border Radius"
                    min={0}
                    max={24}
                    value={ec.captionBorderRadius ?? settings.captionBorderRadius ?? 8}
                    onChange={(val) => setEdit("captionBorderRadius", val)}
                    unit="px"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <Slider
                    label="Outline Thickness"
                    min={0}
                    max={10}
                    value={ec.captionOutlineSize ?? settings.captionOutlineSize ?? 3}
                    onChange={(val) => setEdit("captionOutlineSize", val)}
                    unit="px"
                  />
                  <Slider
                    label="Shadow Offset"
                    min={0}
                    max={10}
                    value={ec.captionShadowSize ?? settings.captionShadowSize ?? 2}
                    onChange={(val) => setEdit("captionShadowSize", val)}
                    unit="px"
                  />
                </div>

                <Slider
                  label="Caption Opacity"
                  min={10}
                  max={100}
                  value={ec.captionOpacity ?? settings.captionOpacity ?? 100}
                  onChange={(val) => setEdit("captionOpacity", val)}
                  unit="%"
                />

                <hr className="border-gray-100" />

                {/* Color pickers */}
                <div className="grid grid-cols-2 gap-3">
                  <ColorPicker
                    label="Text Color"
                    value={ec.captionTextColor ?? settings.captionTextColor ?? ec.textColor ?? "#ffffff"}
                    onChange={(val) => setEdit("captionTextColor", val)}
                  />
                  <ColorPicker
                    label="Highlight Accent"
                    value={ec.captionHighlightColor ?? settings.captionHighlightColor ?? "#ffff00"}
                    onChange={(val) => setEdit("captionHighlightColor", val)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <ColorPicker
                    label="Background Box Color"
                    value={ec.captionBgColor ?? settings.captionBgColor ?? "#000000"}
                    onChange={(val) => setEdit("captionBgColor", val)}
                  />
                  <ColorPicker
                    label="Outline Stroke Color"
                    value={ec.captionOutlineColor ?? settings.captionOutlineColor ?? "#000000"}
                    onChange={(val) => setEdit("captionOutlineColor", val)}
                  />
                </div>

                <div className="flex justify-start">
                  <ColorPicker
                    label="Shadow Offset Color"
                    value={ec.captionShadowColor ?? settings.captionShadowColor ?? "#000000"}
                    onChange={(val) => setEdit("captionShadowColor", val)}
                  />
                </div>
              </div>
            </details>
          </div>
        )}

        {/* ── 3. Hook (Unified Auto Hook) ── */}
        {editorTab === "hook" && (() => {
          const isHookEnabled = ec.autoHook !== undefined 
            ? Boolean(ec.autoHook) 
            : (selectedClip?.autoHook !== undefined ? Boolean(selectedClip.autoHook) : Boolean(settings.autoHook ?? false));
          return (
            <div className="space-y-4 max-h-[520px] overflow-y-auto pr-1 animate-fade-in">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-4">
                <Toggle
                  label="Enable Auto Hook"
                  description="Attention-grabbing hook overlay at clip opening"
                  checked={isHookEnabled}
                  onChange={(checked) => setEdit("autoHook", checked)}
                />

                {isHookEnabled && (
                  <div className="space-y-4 pt-4 border-t border-gray-100 animate-fade-in">
                  <div className="space-y-1.5">
                    <label className="field-label">Hook Text</label>
                    <textarea
                      value={ec.autoHookText ?? ec.hook ?? ""}
                      onChange={(e) => setEdit("autoHookText", e.target.value)}
                      rows={2}
                      placeholder="AI-generated hook text for this clip"
                      className="input-field resize-none"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label className="field-label">Font Family</label>
                      <select
                        value={ec.autoHookFont ?? settings.autoHookFont ?? "Arial Black"}
                        onChange={(e) => setEdit("autoHookFont", e.target.value)}
                        className="input-field"
                      >
                        {["Arial", "Arial Black", "Helvetica", "Impact", "Verdana", "Georgia", "Courier New"].map((f) => (
                          <option key={f} value={f}>{f}</option>
                        ))}
                      </select>
                    </div>
                    <Slider label="Font Size" min={24} max={160} value={ec.autoHookFontSize ?? settings.autoHookFontSize ?? 120} onChange={(val) => setEdit("autoHookFontSize", val)} unit="px" />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <ColorPicker label="Hook Text Color" value={ec.autoHookColor ?? settings.autoHookColor ?? "#ffffff"} onChange={(val) => setEdit("autoHookColor", val)} />
                    <ColorPicker label="Background Color" value={ec.autoHookBgColor ?? settings.autoHookBgColor ?? "#000000"} onChange={(val) => setEdit("autoHookBgColor", val)} />
                  </div>

                  <div>
                    <label className="field-label mb-3">Hook Position</label>
                    <div className="segment-root">
                      {(["top", "top-center", "middle"] as const).map((pos) => (
                        <button
                          key={pos}
                          type="button"
                          className={`segment-option ${(ec.autoHookPosition ?? settings.autoHookPosition ?? "top-center") === pos ? "active" : ""}`}
                          onClick={() => setEdit("autoHookPosition", pos)}
                        >
                          {pos.replace("-", " ")}
                        </button>
                      ))}
                    </div>
                  </div>



                  <div className="border-t border-gray-100 pt-4 space-y-4">
                    <div>
                      <label className="field-label mb-2">Hook Duration Mode</label>
                      <div className="segment-root">
                        <button
                          type="button"
                          className={`segment-option ${(ec.autoHookDurationMode ?? settings.autoHookDurationMode ?? "custom") === "custom" ? "active" : ""}`}
                          onClick={() => setEdit("autoHookDurationMode", "custom")}
                        >
                          Custom Duration
                        </button>
                        <button
                          type="button"
                          className={`segment-option ${(ec.autoHookDurationMode ?? settings.autoHookDurationMode ?? "custom") === "entire" ? "active" : ""}`}
                          onClick={() => setEdit("autoHookDurationMode", "entire")}
                        >
                          Entire Video
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className={(ec.autoHookDurationMode ?? settings.autoHookDurationMode ?? "custom") === "entire" ? "opacity-40 pointer-events-none" : ""}>
                        <Slider
                          label="Visual Duration"
                          min={1}
                          max={10}
                          value={ec.autoHookDuration ?? settings.autoHookDuration ?? 5}
                          onChange={(val) => setEdit("autoHookDuration", val)}
                          unit="s"
                          disabled={(ec.autoHookDurationMode ?? settings.autoHookDurationMode ?? "custom") === "entire"}
                        />
                      </div>
                      <Slider label="Fade In" min={0} max={1000} step={50} value={ec.autoHookFadeIn ?? settings.autoHookFadeIn ?? 300} onChange={(val) => setEdit("autoHookFadeIn", val)} unit="ms" />
                    </div>
                    <Slider label="Fade Out" min={0} max={1000} step={50} value={ec.autoHookFadeOut ?? settings.autoHookFadeOut ?? 500} onChange={(val) => setEdit("autoHookFadeOut", val)} unit="ms" />
                  </div>
                </div>
              )}
            </div>
          </div>
          );
        })()}

        {/* ── 4. Layout ── */}
        {editorTab === "layout" && (() => {
          const selectedLayout = ec.layoutMode ?? selectedClip?.layoutMode ?? settings.layoutMode ?? "auto";
          const actualLayout = selectedClip?.resolvedLayout ?? selectedClip?.crop?.resolvedLayout ?? selectedClip?.crop?.layoutMode ?? selectedClip?.layoutMode ?? "full-crop";
          return (
            <div className="space-y-5 animate-fade-in">
              <div>
                <label className="field-label mb-3">Framing Mode</label>
                <div className="space-y-2">
                  {[
                    {
                      id: "auto",
                      label: "Auto Detection",
                      desc: `Speaker focus with blurred backup logic (Active framing: ${actualLayout === "blur-pad" ? "Smart Vertical Blur" : "Full Vertical Crop"})`,
                    },
                    { id: "full-crop", label: "Full Vertical Crop", desc: "Lock tracking center on face track" },
                    { id: "blur-pad", label: "Smart Vertical Blur", desc: "Original landscape with mirror blur padding" },
                  ].map((mode) => (
                    <button
                      key={mode.id}
                      type="button"
                      className={`w-full rounded-xl border p-4 text-left transition-all ${
                        selectedLayout === mode.id
                          ? "border-gray-950 bg-gray-950 text-white"
                          : "border-gray-200 bg-white hover:border-gray-400 text-gray-700"
                      }`}
                      onClick={() => setEdit("layoutMode", mode.id)}
                    >
                      <span className="block text-sm font-semibold">{mode.label}</span>
                      <span className={`block text-xs mt-0.5 ${selectedLayout === mode.id ? "text-gray-300" : "text-gray-400"}`}>{mode.desc}</span>
                    </button>
                  ))}
                </div>
              </div>
              <Slider label="Blur Strength" min={1} max={60} value={ec.blurStrength ?? selectedClip?.blurStrength ?? 20} onChange={(val) => setEdit("blurStrength", val)} />
            </div>
          );
        })()}

        {/* ── 5. Music ── */}
        {editorTab === "music" && (() => {
          const isMusicEnabled = ec.backgroundMusic !== undefined
            ? Boolean(ec.backgroundMusic)
            : settings.backgroundMusic !== undefined
            ? Boolean(settings.backgroundMusic)
            : Boolean(ec.musicTrack);
          return (
            <div className="space-y-5 animate-fade-in">
              <Toggle
                label="Enable Background Music"
                description="Mix secondary backdrop track over vocals"
                checked={isMusicEnabled}
                onChange={(checked) => setEdit("backgroundMusic", checked)}
              />
              <Slider
                label="Backtrack Volume"
                min={0}
                max={100}
                value={ec.musicVolume ?? settings.musicVolume ?? 20}
                onChange={(val) => setEdit("musicVolume", val)}
                unit="%"
              />

              {isMusicEnabled && (
                <div className="space-y-4 pt-4 border-t border-gray-100 animate-fade-in">
                <div className="space-y-1.5">
                  <label className="field-label">Background Track</label>
                  {musicTracks.length > 0 ? (
                    <select
                      value={ec.musicTrack ?? ""}
                      onChange={(e) => setEdit("musicTrack", e.target.value)}
                      className="input-field"
                    >
                      <option value="">-- Select Music Track --</option>
                      {musicTracks.map((track) => (
                        <option key={track.path} value={track.path}>
                          {track.name.replace(/\.[^/.]+$/, "")}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-xs text-gray-400 italic block">
                      No background tracks found in your assets library.
                    </span>
                  )}
                </div>
              </div>
            )}
            </div>
          );
        })()}

        {/* ── 6. Meme ── */}
        {editorTab === "meme" && (
          <div className="space-y-4 max-h-[520px] overflow-y-auto pr-1 animate-fade-in">
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-semibold text-gray-950 block">Prepend Meme Hook</span>
                  <span className="text-xs text-gray-400">Insert meme clip at start of video</span>
                </div>
                <input
                  type="checkbox"
                  checked={!!ec.memePath}
                  onChange={(e) => {
                    if (!e.target.checked) setEdit("memePath", null);
                    else if (memes.length > 0) setEdit("memePath", memes[0].path);
                  }}
                  className="w-4 h-4 accent-gray-950 rounded"
                />
              </div>

              {ec.memePath && (
                <div className="space-y-4 pt-4 border-t border-gray-100 animate-fade-in">
                  <div className="rounded-lg bg-blue-50 border border-blue-100 p-3 text-xs text-blue-700">
                    Duration is automatically adjusted based on uploaded meme length.
                  </div>

                  <div>
                    <label className="field-label mb-2">Upload Meme Video</label>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          const input = document.createElement("input");
                          input.type = "file";
                          input.accept = "video/*";
                          input.onchange = (e: any) => {
                            const file = e.target.files?.[0];
                            if (file) handleAssetUpload("memes", file);
                          };
                          input.click();
                        }}
                      >
                        Upload Video
                      </Button>
                      <span className="text-xs text-gray-400">MP4, WEBM</span>
                    </div>
                  </div>

                  <div>
                    <label className="field-label mb-2">Select Clip</label>
                    {memes.length > 0 ? (
                      <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                        {memes.map((m) => (
                          <button
                            key={m.name}
                            type="button"
                            className={`w-full flex items-center justify-between rounded-lg border p-2.5 text-left text-xs transition-all ${
                              ec.memePath === m.path
                                ? "border-gray-950 bg-gray-950 text-white"
                                : "border-gray-200 bg-white text-gray-700 hover:border-gray-400"
                            }`}
                            onClick={() => setEdit("memePath", m.path)}
                          >
                            <span className="truncate max-w-[80%]">{m.name}</span>
                            {ec.memePath === m.path && <span className="text-[10px] text-white/70">Selected</span>}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400 italic block">No meme clips uploaded yet.</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── 7. Export ── */}
        {editorTab === "export" && (
          <div className="space-y-5 animate-fade-in">
            <div>
              <label className="field-label mb-3">Export Aspect Ratio</label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "9:16", label: "Vertical", desc: "9:16 portrait" },
                  { id: "1:1", label: "Square", desc: "1:1 social" },
                  { id: "16:9", label: "Landscape", desc: "16:9 widescreen" },
                ].map((frame) => (
                  <button
                    key={frame.id}
                    type="button"
                    className={`rounded-xl border p-4 text-center transition-all ${
                      (ec.frameAspect ?? "9:16") === frame.id
                        ? "border-gray-950 bg-gray-950 text-white"
                        : "border-gray-200 bg-white hover:border-gray-400 text-gray-700"
                    }`}
                    onClick={() => setEdit("frameAspect", frame.id)}
                  >
                    <span className="block text-sm font-semibold">{frame.label}</span>
                    <span className={`block text-xs mt-0.5 ${(ec.frameAspect ?? "9:16") === frame.id ? "text-gray-300" : "text-gray-400"}`}>{frame.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2 border-t border-gray-100 pt-5">
              <label className="field-label mb-2">Downloads</label>
              <Button
                variant="secondary"
                className="w-full justify-start"
                onClick={() => {
                  if (!activeJobId || !selectedClip.id) return;
                  window.open(`http://localhost:3001/api/results/${activeJobId}/clips/${selectedClip.id}?t=${Date.now()}`, "_blank");
                }}
              >
                Download MP4 Clip
              </Button>
              <Button
                variant="secondary"
                className="w-full justify-start"
                onClick={() => {
                  if (!activeJobId || !selectedClip.id) return;
                  window.open(
                    `http://localhost:3001/api/results/${activeJobId}/thumbnails/${selectedClip.id}?t=${Date.now()}`,
                    "_blank"
                  );
                }}
              >
                Download Cover Thumbnail
              </Button>
              <Button
                variant="secondary"
                className="w-full justify-start"
                onClick={exportSelected}
                disabled={!activeJobId || selectedClipIds.length === 0}
              >
                Download Selected ZIP ({selectedClipIds.length})
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
