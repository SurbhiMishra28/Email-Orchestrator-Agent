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
        // Every colour is a CSS variable holding space-separated RGB channels,
        // so Tailwind's opacity modifiers (`bg-ink-100/95`) keep working and a
        // theme swap is a variable change rather than a class rewrite.
        // The ramps are inverted: 50 is the page floor, 900 the brightest text
        // (dark theme) or the darkest text (light theme).
        brand: {
          50: "rgb(var(--brand-50) / <alpha-value>)",
          100: "rgb(var(--brand-100) / <alpha-value>)",
          200: "rgb(var(--brand-200) / <alpha-value>)",
          300: "rgb(var(--brand-300) / <alpha-value>)",
          400: "rgb(var(--brand-400) / <alpha-value>)",
          500: "rgb(var(--brand-500) / <alpha-value>)",
          600: "rgb(var(--brand-600) / <alpha-value>)",
          700: "rgb(var(--brand-700) / <alpha-value>)",
          800: "rgb(var(--brand-800) / <alpha-value>)",
          900: "rgb(var(--brand-900) / <alpha-value>)",
        },
        ink: {
          50: "rgb(var(--ink-50) / <alpha-value>)",
          100: "rgb(var(--ink-100) / <alpha-value>)",
          200: "rgb(var(--ink-200) / <alpha-value>)",
          300: "rgb(var(--ink-300) / <alpha-value>)",
          400: "rgb(var(--ink-400) / <alpha-value>)",
          500: "rgb(var(--ink-500) / <alpha-value>)",
          600: "rgb(var(--ink-600) / <alpha-value>)",
          700: "rgb(var(--ink-700) / <alpha-value>)",
          800: "rgb(var(--ink-800) / <alpha-value>)",
          900: "rgb(var(--ink-900) / <alpha-value>)",
        },
        card: "rgb(var(--card) / <alpha-value>)",
        danger: {
          50: "rgb(var(--danger-50) / <alpha-value>)",
          100: "rgb(var(--danger-100) / <alpha-value>)",
          200: "rgb(var(--danger-200) / <alpha-value>)",
          500: "rgb(var(--danger-500) / <alpha-value>)",
          600: "rgb(var(--danger-600) / <alpha-value>)",
          700: "rgb(var(--danger-700) / <alpha-value>)",
          800: "rgb(var(--danger-800) / <alpha-value>)",
        },
        warn: {
          50: "rgb(var(--warn-50) / <alpha-value>)",
          100: "rgb(var(--warn-100) / <alpha-value>)",
          200: "rgb(var(--warn-200) / <alpha-value>)",
          500: "rgb(var(--warn-500) / <alpha-value>)",
          600: "rgb(var(--warn-600) / <alpha-value>)",
          700: "rgb(var(--warn-700) / <alpha-value>)",
          800: "rgb(var(--warn-800) / <alpha-value>)",
        },
        info: {
          50: "rgb(var(--info-50) / <alpha-value>)",
          100: "rgb(var(--info-100) / <alpha-value>)",
          200: "rgb(var(--info-200) / <alpha-value>)",
          500: "rgb(var(--info-500) / <alpha-value>)",
          600: "rgb(var(--info-600) / <alpha-value>)",
          700: "rgb(var(--info-700) / <alpha-value>)",
        },
      },
      borderRadius: {
        card: "14px",
      },
      boxShadow: {
        card: "0 1px 0 rgba(255, 255, 255, 0.03) inset, 0 8px 24px rgba(0, 0, 0, 0.28)",
        pop: "0 24px 64px rgba(0, 0, 0, 0.55), 0 2px 8px rgba(0, 0, 0, 0.4)",
        rail: "1px 0 0 rgba(255, 255, 255, 0.05)",
        glow: "0 0 60px rgba(127, 179, 157, 0.18)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        drift: {
          "0%, 100%": { transform: "translate3d(0, 0, 0) scale(1)" },
          "50%": { transform: "translate3d(2%, -1.5%, 0) scale(1.06)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out both",
        drift: "drift 26s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};