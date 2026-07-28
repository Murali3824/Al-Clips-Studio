/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        heading: ["Geist", "sans-serif"],
      },
      colors: {
        brand: {
          blue: "#2563EB",
        },
      },
      animation: {
        "fade-in": "fadeIn 0.2s ease-out both",
        "slide-up": "slideUp 0.25s cubic-bezier(0.16,1,0.3,1) both",
        "scale-in": "scaleIn 0.2s ease-out both",
        "pulse-slow": "pulse 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          from: { opacity: "0", transform: "scale(0.95)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },
    },
  },
  plugins: [],
};
