import React from "react";
import { TranslationLanguage } from "../../types/settings";

interface TranslationSettingsProps {
  settings: any;
  languages: any[];
  toggleLanguage: (language: any) => void;
}

export const TranslationSettings: React.FC<TranslationSettingsProps> = ({
  settings,
  languages,
  toggleLanguage,
}) => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-gray-100 pb-5 mb-5">
        <h3 className="text-lg font-semibold text-gray-950 font-[Geist]">
          Translation
        </h3>
      </div>

      <div className="space-y-5">
        <div>
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide block mb-2">Choose Translation Target</span>
          <p className="text-xs text-gray-400 mb-4 select-none">
            Generates secondary vertical clips dubbed or subbed in target languages.
          </p>
          
          <div className="flex flex-wrap gap-2">
            {languages.map((lang) => {
              const isActive = settings.translationLanguages?.includes(lang.id);
              return (
                <button
                  key={lang.id}
                  type="button"
                  className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-gray-950 text-white shadow-sm"
                      : "bg-white border border-gray-200 text-gray-600 hover:border-gray-400 hover:bg-gray-50"
                  }`}
                  onClick={() => toggleLanguage(lang.id)}
                >
                  {lang.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
