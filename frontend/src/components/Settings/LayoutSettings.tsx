import React from "react";
import { Slider } from "../Common/Slider";

interface LayoutSettingsProps {
  settings: any;
  updateSetting: (key: any, value: any) => void;
}

export const LayoutSettings: React.FC<LayoutSettingsProps> = ({
  settings,
  updateSetting,
}) => {
  const currentMode = settings.layoutMode ?? "auto";

  const options = [
    {
      id: "auto",
      title: "Auto Detection (Recommended)",
      desc: "Automatically switches between Full Vertical Crop and Smart Vertical Blur based on the detected scene.",
    },
    {
      id: "full-crop",
      title: "Full Vertical Crop",
      desc: "Locks the active speaker in a 9:16 vertical crop.",
    },
    {
      id: "blur-pad",
      title: "Smart Vertical Blur",
      desc: "Keeps the original landscape framing with blurred background padding.",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-gray-100 pb-5 mb-5">
        <div>
          <h3 className="text-lg font-semibold text-gray-950 font-[Geist]">
            Video Layout
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            Choose the default framing and aspect layout for generated clips.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">
          Framing Mode
        </span>

        <div className="grid gap-3">
          {options.map((opt) => {
            const isSelected = currentMode === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                className={`w-full rounded-xl border p-4 text-left transition-all ${
                  isSelected
                    ? "border-gray-950 bg-gray-950 text-white shadow-sm"
                    : "border-gray-200 bg-white hover:border-gray-400 text-gray-700"
                }`}
                onClick={() => updateSetting("layoutMode", opt.id)}
              >
                <div className="flex items-center justify-between">
                  <span className={`font-semibold text-sm ${isSelected ? "text-white" : "text-gray-950"}`}>
                    {opt.title}
                  </span>
                  {isSelected && (
                    <span className="text-xs bg-white/20 text-white px-2 py-0.5 rounded-full font-medium">
                      Selected
                    </span>
                  )}
                </div>
                <p className={`text-xs mt-1 leading-relaxed ${isSelected ? "text-gray-300" : "text-gray-400"}`}>
                  {opt.desc}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Blur Strength slider when blur-pad or auto is selected */}
      {(currentMode === "blur-pad" || currentMode === "auto") && (
        <div className="pt-2 animate-fade-in space-y-2">
          <Slider
            label="Blur Strength"
            min={1}
            max={60}
            value={settings.blurStrength ?? 20}
            onChange={(val) => updateSetting("blurStrength", val)}
          />
          <p className="text-[11px] text-gray-400">
            Controls the Gaussian blur intensity applied to background padding.
          </p>
        </div>
      )}
    </div>
  );
};
