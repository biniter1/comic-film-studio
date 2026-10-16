/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#090d16",
        surface: "#111827",
        "surface-raised": "#1f2937",
        border: "#374151",
        primary: {
          DEFAULT: "#8b5cf6",
          hover: "#7c3aed",
        },
      },
    },
  },
  plugins: [],
}
