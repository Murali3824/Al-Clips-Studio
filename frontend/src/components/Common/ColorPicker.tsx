import React from "react";

interface ColorPickerProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export const ColorPicker: React.FC<ColorPickerProps> = ({
  label,
  value,
  onChange,
  disabled = false,
}) => {
  return (
    <div className={`space-y-1.5 ${disabled ? "opacity-40 pointer-events-none" : ""}`}>
      {label && (
        <span className="block text-xs font-medium text-gray-500 uppercase tracking-wide">
          {label}
        </span>
      )}
      <div className="flex items-center gap-2">
        <div
          className="w-8 h-8 rounded-lg border border-gray-200 flex-shrink-0 shadow-sm"
          style={{ backgroundColor: value }}
        />
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full h-8 rounded-lg border border-gray-200 cursor-pointer bg-white p-0.5"
          title={label}
        />
      </div>
    </div>
  );
};
