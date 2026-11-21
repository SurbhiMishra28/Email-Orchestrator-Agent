/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        brand: {
          50: "#eff8ff",
          100: "#dbeefe",
          200: "#bfe2fd",
          300: "#93d0fb",
          400: "#60b6f7",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
          800: "#075985",
          900: "#0c4a6e",
        },
        ink: {
          50: "#f7f8fa",
          100: "#eef0f4",
          200: "#e2e5eb",
          300: "#cfd4dd",
          400: "#9aa2b1",
          500: "#6b7484",
          600: "#4c5462",
          700: "#39404c",
          800: "#252b34",
          900: "#141a21",
        },
      },
      borderRadius: {
        card: "12px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(19, 27, 38, 0.04), 0 1px 3px rgba(19, 27, 38, 0.06)",
        pop: "0 12px 32px rgba(19, 27, 38, 0.14), 0 2px 6px rgba(19, 27, 38, 0.06)",
        rail: "1px 0 0 rgba(19, 27, 38, 0.07)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out both",
      },
    },
  },
  plugins: [],
};
