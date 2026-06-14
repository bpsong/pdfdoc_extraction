import daisyui from "daisyui";

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [daisyui],
  daisyui: {
    themes: [
      {
        docflow: {
          primary: "#4f46e5",
          secondary: "#0f766e",
          accent: "#7c3aed",
          neutral: "#111827",
          "base-100": "#ffffff",
          "base-200": "#f6f7fb",
          "base-300": "#e5e7eb",
          info: "#2563eb",
          success: "#16a34a",
          warning: "#d97706",
          error: "#dc2626",
        },
      },
    ],
  },
};
