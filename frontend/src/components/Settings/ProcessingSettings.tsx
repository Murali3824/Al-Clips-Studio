import React from "react";
import { Slider } from "../Common/Slider";
import { Toggle } from "../Common/Toggle";
import { Button } from "../Common/Button";
import { WhisperModel } from "../../types/settings";

interface ProcessingSettingsProps {
  settings: any;
  updateSetting: (key: any, value: any) => void;
  saveSettings: () => void;
  hasMusicLibrary: boolean;
  musicDownloading: boolean;
  onDownloadMusic: () => void;
  processMessage: string | null;
  onStartProcessing: () => void;
  job: any;
}

export const ProcessingSettings: React.FC<ProcessingSettingsProps> = ({
  settings,
  updateSetting,
  saveSettings,
  hasMusicLibrary,
  musicDownloading,
  onDownloadMusic,
}) => {
  return (
    <div className="space-y-5">
      <div className="border-b border-gray-100 pb-5 mb-5">
        <h3 className="text-lg font-semibold text-gray-950 font-[Geist]">
          AI Configuration
        </h3>
      </div>

      <div className="space-y-6">
        {/* Clip Generation Mode */}
        <div className="grid gap-2">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">
            Clip Generation Mode
          </span>
          <div className="grid grid-cols-2 gap-1 bg-gray-100 p-1 rounded-lg">
            <button
              type="button"
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                settings.clipGenerationMode === "auto"
                  ? "bg-white shadow-sm text-gray-950 border border-gray-200"
                  : "text-gray-500 hover:text-gray-700 border border-transparent"
              }`}
              onClick={() => updateSetting("clipGenerationMode", "auto")}
            >
              ✨ Auto
            </button>
            <button
              type="button"
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                settings.clipGenerationMode === "manual"
                  ? "bg-white shadow-sm text-gray-950 border border-gray-200"
                  : "text-gray-500 hover:text-gray-700 border border-transparent"
              }`}
              onClick={() => updateSetting("clipGenerationMode", "manual")}
            >
              🎛️ Manual
            </button>
          </div>
        </div>

        {/* Dynamic Options based on Clip Generation Mode */}
        {settings.clipGenerationMode === "auto" ? (
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600 leading-relaxed">
            <span className="font-semibold text-gray-950 block mb-1">🤖 Dynamic Clip Slicing</span>
            AI automatically determines the best clip count, boundary margins, and optimal durations based on natural topic pauses and highlight density. Genuinely weak moments are skipped.
          </div>
        ) : (
          <div className="space-y-5 pt-1 animate-fade-in">
            {/* Maximum Clip Count Slider */}
            <Slider
              label="Maximum Clip Count"
              min={1}
              max={20}
              value={settings.clipCount}
              onChange={(val) => updateSetting("clipCount", val)}
            />

            {/* Preferred Duration Dropdown */}
            <div className="grid gap-2">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">Preferred Clip Duration</span>
              <select
                className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-950 focus:ring-2 focus:ring-black/5 outline-none appearance-none cursor-pointer transition-all hover:border-gray-300"
                value={settings.preferredDuration}
                onChange={(e) => updateSetting("preferredDuration", e.target.value as any)}
              >
                <option value="auto">Auto (Recommended based on context)</option>
                <option value="short">Short (15 – 30 seconds)</option>
                <option value="medium">Medium (30 – 60 seconds)</option>
                <option value="long">Long (60 – 90 seconds)</option>
              </select>
            </div>
          </div>
        )}

        {/* Coverage Mode Selector */}
        <div className="grid gap-2">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">
            Timeline Coverage Mode
          </span>
          <div className="grid grid-cols-2 gap-1 bg-gray-100 p-1 rounded-lg">
            <button
              type="button"
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                settings.coverageMode === "best"
                  ? "bg-white shadow-sm text-gray-950 border border-gray-200"
                  : "text-gray-500 hover:text-gray-700 border border-transparent"
              }`}
              onClick={() => updateSetting("coverageMode", "best")}
            >
              🔥 Best Moments
            </button>
            <button
              type="button"
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                settings.coverageMode === "entire"
                  ? "bg-white shadow-sm text-gray-950 border border-gray-200"
                  : "text-gray-500 hover:text-gray-700 border border-transparent"
              }`}
              onClick={() => updateSetting("coverageMode", "entire")}
            >
              🌐 Entire Coverage
            </button>
          </div>
          <span className="text-xs text-gray-400 block mt-1">
            {settings.coverageMode === "best"
              ? "Selects the strongest viral moments regardless of their position on the timeline."
              : "Spreads selections across the entire timeline (early, middle, late) so later parts are not ignored."}
          </span>
        </div>

        {/* Whisper Model selection */}
        <div className="grid gap-2">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">Whisper Model Size</span>
          <select
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-950 focus:ring-2 focus:ring-black/5 outline-none appearance-none cursor-pointer transition-all hover:border-gray-300"
            value={settings.whisperModel}
            onChange={(e) => updateSetting("whisperModel", e.target.value as WhisperModel)}
          >
            <option value="tiny">Tiny (Fastest)</option>
            <option value="medium">Medium (Balanced)</option>
            <option value="large-v3">Large v3 (Most Accurate)</option>
          </select>
        </div>

        <hr className="border-gray-100 my-5" />

        <details className="group [&_summary::-webkit-details-marker]:hidden">
          <summary className="flex cursor-pointer items-center justify-between text-sm font-semibold text-gray-950 outline-none">
            Advanced Settings
            <span className="transition duration-200 group-open:-rotate-180">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-gray-500"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </span>
          </summary>

          <div className="mt-5 space-y-6 pb-2">
            {/* Processing Feature Toggles */}
            <div className="grid grid-cols-2 gap-5">
              <Toggle
                label="Diarization"
                description="Separate speakers"
                checked={Boolean(settings.speakerDiarization)}
                onChange={(checked) => updateSetting("speakerDiarization", checked)}
              />
              <Toggle
                label="Music Sync"
                description="Add backtracks"
                checked={Boolean(settings.backgroundMusic)}
                onChange={(checked) => updateSetting("backgroundMusic", checked)}
              />
              <Toggle
                label="Thumbnails"
                description="Export covers"
                checked={Boolean(settings.thumbnailGeneration)}
                onChange={(checked) => updateSetting("thumbnailGeneration", checked)}
              />
              <Toggle
                label="Remove Silence"
                description="Cut dead space"
                checked={Boolean(settings.silenceRemoval)}
                onChange={(checked) => updateSetting("silenceRemoval", checked)}
              />
            </div>

            {/* Conditional Music Library Installer */}
            {settings.backgroundMusic && !hasMusicLibrary && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-fade-in select-none">
                <span>Music library assets are not installed.</span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={musicDownloading}
                  onClick={onDownloadMusic}
                  className="bg-white text-amber-700 border-amber-200 hover:bg-amber-100 whitespace-nowrap"
                >
                  {musicDownloading ? "Installing..." : "Download Library"}
                </Button>
              </div>
            )}

            {/* Conditional Music Volume Slider */}
            {settings.backgroundMusic && (
              <div className="animate-fade-in">
                <Slider
                  label="Music Volume"
                  min={0}
                  max={100}
                  value={settings.musicVolume}
                  disabled={!hasMusicLibrary}
                  onChange={(val) => updateSetting("musicVolume", val)}
                  unit="%"
                />
              </div>
            )}
          </div>
        </details>
      </div>
    </div>
  );
};
